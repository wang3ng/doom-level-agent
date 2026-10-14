"""Stage 2: text (+ optional image path) -> layout JSON via Ollama."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

DEFAULT_API = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("LAYOUT_MODEL", "qwen3-coder:30b")

from pipeline.design_detail import (  # noqa: E402
    LAYOUT_JSON_COMPACT,
    PART_DESIGN_JSON_HINT,
    PART_DESIGN_RULES,
    WRITER_PLAYTEST_HAZARDS,
)

SYSTEM = f"""You are a Doom level layout planner (JSON→WAD Stage 2).
Output ONLY valid JSON matching this shape:
{{
  "name": "string",
  "theme": "string",
  "brief": "string",
  "objective_room": "exit_id",
  "part_designs": [{{"id":"service_choke","role":"choke","shape":"narrow 192x128","elevation":"...","cover":"...","mobs":"...","triggers":"...","light":"...","textures":"...","detail":"..."}}],
  "rooms": [{{"id":"r1","x":0,"y":0,"w":256,"h":256,"floor_height":0,"ceiling_height":128,"floor_flat":"FLOOR0_1","ceil_flat":"CEIL1_1","wall_texture":"STARTAN3","light":220,"shape":"narrow","design":"..."}}],
  "connections": [{{"a":"r1","b":"r2","kind":"corridor","width":64,"lock":"yellow","design":"..."}}],
  "props": [{{"type":"cover_block","x":280,"y":200,"w":32,"h":32,"floor_raise":32,"in_room":"service_choke","design":"peek cover OFF walk midline"}}],
  "closets": [{{"id":"arena_ambush","attach_room":"combat_arena","side":"east","trigger":"walk","design":"...","monsters":[{{"type":"Imp","dx":40,"dy":40,"angle":180}}]}}],
  "things": [{{"type":"Player1Start","x":128,"y":128,"angle":0}}]
}}
Format compact:
{LAYOUT_JSON_COMPACT}
Rules:
- Axis-aligned rooms only; sizes multiples of 64; coordinates integers.
- Exactly one Player1Start inside some room (not inside a prop).
- Exactly one ExitSwitch inside the exit/objective room (far wall).
- Prefer hub topology: key in a side wing, return to hub, then locked door to arena/exit.
- If a connection has "lock": "blue"|"yellow"|"red", place the matching BlueCard/YellowCard/RedCard off the locked path so the player must detour then return.
- Connections must reference existing room ids; graph should be connected.
- Prefer 6-8 rooms with a clear critical path and a hub when the brief asks for one.
- Leave geometric GAPS between room rectangles (do not overlap) so corridors can be inserted.
- Prefer true L footprints: shape "L" + wing_side/wing_w/wing_h on ONE room (not a separate wing room).
- Connection kind may be corridor, door, open, or lift. Locked links use kind "door" plus lock color. Rideable height changes use kind "lift".
- Set objective_room to the exit room id.
- Use free Doom texture names (STARTAN3, BROWN96, SLADWALL, GSTONE1, COMPSPAN, FLOOR0_1, NUKAGE1, …).
- Honor light levels and room roles stated in the brief when present.
- ALWAYS fill part_designs for every room (and important doors). Honor those notes in rooms/props/closets.
{PART_DESIGN_RULES}
{WRITER_PLAYTEST_HAZARDS}
Example part_designs:
{PART_DESIGN_JSON_HINT}
- No markdown fences.
"""


def _chat(prompt: str, model: str = DEFAULT_MODEL, api_base: str = DEFAULT_API) -> str:
    url = api_base.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.35},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["message"]["content"]


def brief_to_layout(
    brief: str,
    *,
    image_hint: str | None = None,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API,
    use_few_shot: bool = True,
    few_shot_k: int = 3,
    use_classic: bool = True,
    classic_k: int = 2,
) -> dict[str, Any]:
    user = f"Design a small playable Doom layout for this brief:\n{brief}\n"
    if use_classic:
        try:
            from pipeline.design_detail import classic_guidance_for

            classic = classic_guidance_for(brief, k=classic_k)
            if classic:
                user += (
                    "\nImitate the CLASSIC DOOM micro-design depth below "
                    "(do NOT copy room ids; invent a new map):\n"
                    + classic
                    + "\n"
                )
        except Exception:
            pass
    if use_few_shot:
        try:
            from corpus.fewshot import format_few_shot_block, select_few_shot

            examples = select_few_shot(brief, k=few_shot_k)
            if examples:
                user += "\nUse these corpus examples as style/structure references (do NOT copy room ids):\n"
                user += format_few_shot_block(examples)
                user += "\n"
        except Exception:
            pass
    if image_hint:
        user += f"\nConcept image notes / path: {image_hint}\n"
    user += (
        "Return JSON only. Every room must have a matching part_designs entry "
        "with measurable shape/elevation/cover/mobs/triggers/light/textures/detail. "
        "Obey WRITER_PLAYTEST_HAZARDS (clear walk lanes, true L rooms, lift kinds, "
        "portal margins on wing faces, no closet/exit overlap)."
    )
    raw = _chat(user, model=model, api_base=api_base)
    return json.loads(raw)
