#!/usr/bin/env python3
"""Generate diverse corpus brief cards via Ollama (or templates offline)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_API = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("LAYOUT_MODEL", "qwen3-coder:30b")

SEEDS = [
    {
        "id": "techbase_reactor",
        "theme_hint": "UAC techbase with a glowing reactor landmark",
        "structure": "safe start -> choke corridor -> hub with blue key -> dark service tunnels -> reactor arena -> exit",
        "mechanics": "blue key door; shotgun teach before first Imp pack",
        "tone": "cold fluorescent then red alert",
    },
    {
        "id": "hell_keep",
        "theme_hint": "Hell keep carved from flesh-stone and lava",
        "structure": "cliffside start overlook -> narrow battlements -> courtyard arena -> red skull gate -> throne exit",
        "mechanics": "red skull; vertical drops; no safe backtrack after courtyard",
        "tone": "oppressive, crimson lighting, roar ambience",
    },
    {
        "id": "city_streets",
        "theme_hint": "ruined downtown streets and alley loops",
        "structure": "street spawn -> alley breadcrumb ammo -> courtyard crossfire -> sewer shortcut -> rooftop exit switch",
        "mechanics": "optional sewer secret; yellow door for early armor",
        "tone": "gray daylight, neon signs as landmarks",
    },
    {
        "id": "key_puzzle_hub",
        "theme_hint": "star hub with three keyed wings",
        "structure": "central hub revisited 3 times; blue wing teach; yellow wing escalate; red wing bossy arena then exit in hub",
        "mechanics": "blue/yellow/red cards; hub landmark must stay readable",
        "tone": "clean tech, each wing a different light color",
    },
    {
        "id": "vertical_silo",
        "theme_hint": "industrial silo with stacked floors",
        "structure": "ground start -> lift teach -> mid catwalk fight -> top control room exit",
        "mechanics": "lift as teach/test; monsters on ledges; health on landings",
        "tone": "echoing metal, bright top vs dark shaft",
    },
    {
        "id": "ambush_warehouse",
        "theme_hint": "warehouse crates and closet ambushes",
        "structure": "quiet loading bay -> crate maze breadcrumbs -> fake dead end closet release -> open loading arena exit",
        "mechanics": "monster closet after shotgun pickup; crate cover",
        "tone": "dusty browns, sudden noise after silence",
    },
    {
        "id": "slime_plant",
        "theme_hint": "toxic plant with damaging floors and bridges",
        "structure": "locker start -> grated bridge over slime -> pump room key -> raised pipe walk -> exit behind yellow door",
        "mechanics": "yellow key; slime as hazard teach with rad suit nearby",
        "tone": "sick green light, dripping pipes",
    },
    {
        "id": "nonlinear_fort",
        "theme_hint": "small fortress with two valid routes to the exit",
        "structure": "gatehouse start; left barracks path (combat heavy); right courtyard path (stealth/ammo); paths merge at keep exit",
        "mechanics": "no keys; branching then merge; one secret tower",
        "tone": "stone and banners, daylight yard vs torch halls",
    },
]

SYSTEM = """You write Doom level corpus cards for few-shot layout planning.
Return ONLY JSON:
{
  "id": "string",
  "theme": "short label",
  "brief": "3-5 specific sentences: start, route, combat, landmark, exit",
  "solution_path": ["named steps in order"],
  "landmarks": ["2-4 concrete landmarks"],
  "pacing_notes": "one sentence",
  "part_designs": [
    {
      "id": "part_id",
      "role": "start|choke|hub|key|arena|exit|closet|optional",
      "shape": "narrow / dogleg / wide hub / square arena / alcove",
      "elevation": "floor/ceiling contrast note",
      "cover": "hallway pillar / raised block / none",
      "mobs": "who uses the space",
      "triggers": "walk closet / locked door / none",
      "light": "bright/dim relative note",
      "textures": "tech / nukage / flesh / outdoor",
      "detail": "one concrete micro-design sentence"
    }
  ],
  "rubric_hints": {
    "navigation": "...",
    "pacing": "...",
    "mechanics": "...",
    "affordances": "...",
    "narrative": "..."
  }
}
Include part_designs for every major space (not just the critical-path summary).
Mention small cover, elevation changes, and triggered monster closets when they fit the theme.
Match the denseness of classic Doom maps (Entryway teach, Nuclear Plant hub+key return, House of Pain shape/mood).
Keep geometry imaginable as axis-aligned rooms + corridors. No markdown.
"""


def _chat(prompt: str, model: str, api_base: str) -> str:
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.55},
    }
    req = urllib.request.Request(
        api_base.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]["content"]


def _template(seed: dict) -> dict:
    steps = [s.strip() for s in seed["structure"].split("->")]
    return {
        "id": seed["id"],
        "source_wad": None,
        "theme": seed["theme_hint"].split(" with ")[0][:48],
        "brief": (
            f"{seed['theme_hint']}. Critical route: {seed['structure']}. "
            f"Mechanics: {seed['mechanics']}. Mood: {seed['tone']}."
        ),
        "solution_path": steps,
        "landmarks": [seed["theme_hint"]],
        "pacing_notes": seed["tone"],
        "rubric_hints": {
            "navigation": f"Landmark and path: {seed['structure']}",
            "pacing": seed["tone"],
            "mechanics": seed["mechanics"],
            "affordances": "Consistent door/key colors and hazard reads.",
            "narrative": seed["theme_hint"],
        },
        "generator": "template",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "corpus" / "cards")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api", default=DEFAULT_API)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for seed in SEEDS:
        if args.ollama:
            from corpus.classic import format_classic_block

            prompt = (
                "Create a corpus card from this seed (keep id unchanged):\n"
                + json.dumps(seed, indent=2)
                + "\n\nMatch this classic Doom micro-design denseness "
                "(do not copy titles/ids):\n"
                + format_classic_block(seed.get("theme_hint", ""), k=2, max_parts=8)
            )
            try:
                card = json.loads(_chat(prompt, args.model, args.api))
                card["id"] = seed["id"]
                card["source_wad"] = None
                card["generator"] = "ollama"
                card["seed"] = seed
            except Exception as exc:  # noqa: BLE001
                card = _template(seed)
                card["error"] = str(exc)
        else:
            card = _template(seed)
        path = args.out_dir / f"{seed['id']}.json"
        path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        written.append(path.name)
        print(f"wrote {path.name}: {card.get('theme')} | {card.get('brief', '')[:80]}...")

    index = {
        "n_cards": len(list(args.out_dir.glob('*.json'))),
        "generated": written,
        "note": "Mix author WAD cards + seeded theme cards for few-shot planning.",
    }
    (args.out_dir.parent / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
