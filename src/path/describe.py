"""LLM description of a level from critical-path extract."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

DEFAULT_API = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("LAYOUT_MODEL", "qwen3-coder:30b")

from pipeline.design_detail import PART_DESIGN_RULES

SYSTEM = f"""You write Doom level design briefs from a critical-path analysis.
Return ONLY JSON:
{{
  "theme": "short theme label",
  "brief": "2-4 sentences, specific about start, route, combat beats, keys/locks, landmark, exit",
  "solution_path": ["step1", "step2", "..."],
  "landmarks": ["..."],
  "pacing_notes": "one sentence",
  "part_designs": [
    {{
      "id": "room_or_part_id",
      "role": "start|choke|hub|key|arena|exit|closet|optional",
      "shape": "narrow / dogleg / wide hub / square arena / alcove / ...",
      "elevation": "floor/ceiling contrasts vs neighbors",
      "cover": "hallway pillar, raised block, none, ...",
      "mobs": "who and how they use space",
      "triggers": "monster closet walk-open, locked door, none",
      "detail": "one concrete sentence of micro-design"
    }}
  ],
  "rubric_hints": {{
    "navigation": "...",
    "pacing": "...",
    "mechanics": "...",
    "affordances": "...",
    "narrative": "..."
  }}
}}
{PART_DESIGN_RULES}
Be concrete. Do not invent keys/exits that are absent from the analysis. No markdown.
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


def describe_from_path(
    path_report: dict[str, Any],
    *,
    path_score: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API,
    offline: bool = False,
) -> dict[str, Any]:
    if offline or not path_report.get("ok"):
        return _template_description(path_report, path_score)

    user = (
        "Write a specific level description from this critical-path analysis:\n"
        + json.dumps({"path": path_report, "clarity_score": path_score}, indent=2)
        + "\n\nWrite part_designs for EVERY major space on and off the path "
        "(shape, elevation, cover, mobs, triggers, light/textures, detail). "
        "Match the depth of classic Doom refs below; invent details consistent "
        "with the analysis — do not invent keys/exits the analysis lacks.\n"
    )
    try:
        from pipeline.design_detail import classic_guidance_for

        theme_hint = str(path_report.get("map") or "") + " " + str((path_score or {}).get("notes") or "")
        classic = classic_guidance_for(theme_hint or "techbase plant hub", k=2)
        if classic:
            user += "\n" + classic + "\n"
    except Exception:
        pass
    try:
        raw = _chat(user, model=model, api_base=api_base)
        data = json.loads(raw)
        data["generator"] = "ollama"
        return data
    except Exception as exc:  # noqa: BLE001
        out = _template_description(path_report, path_score)
        out["generator"] = "template_fallback"
        out["error"] = str(exc)
        return out


def _template_description(
    path_report: dict[str, Any],
    path_score: dict[str, Any] | None,
) -> dict[str, Any]:
    if not path_report.get("ok"):
        return {
            "theme": "unknown",
            "brief": f"Path analysis failed: {path_report.get('error')}",
            "solution_path": [],
            "landmarks": [],
            "pacing_notes": "",
            "rubric_hints": {},
            "generator": "template",
        }
    if path_report.get("source") == "layout_json":
        steps = [f"Enter {r}" for r in path_report.get("path_rooms", [])]
        goal = path_report.get("goal_room")
        brief = (
            f"Start in {path_report.get('start_room')}, follow "
            f"{' -> '.join(path_report.get('path_rooms', []))}, "
            f"objective at {goal}. Clarity score notes: "
            f"{(path_score or {}).get('notes', '')}"
        )
    else:
        steps = [f"Sector {s}" for s in path_report.get("path_sectors", [])]
        keys = path_report.get("keys_collected") or []
        locks = path_report.get("locks_used") or []
        brief = (
            f"MAP {path_report.get('map')}: start sector {path_report.get('start_sector')} "
            f"to sector {path_report.get('goal_sector')} "
            f"({'exit reached' if path_report.get('reached_exit') else 'no exit found'}). "
            f"Keys on path: {keys or 'none'}. Locks used: {len(locks)}. "
            f"Path length {path_report.get('path_length')} sectors "
            f"(coverage {path_report.get('coverage')})."
        )
        if locks:
            steps.append(
                "Unlock "
                + ", ".join(f"{L['key']} gate {L['from']}->{L['to']}" for L in locks)
            )
    return {
        "theme": "from_path_analysis",
        "brief": brief,
        "solution_path": steps,
        "landmarks": [],
        "pacing_notes": (path_score or {}).get("notes", ""),
        "part_designs": [],
        "rubric_hints": {
            "navigation": "Follow extracted critical path; emphasize landmarks at branch points.",
            "pacing": "Place quieter sectors early and denser fights near the goal.",
            "mechanics": "Preserve key gates found on the path." if path_report.get("locks_used") else "Add a teach beat before the first fight.",
            "affordances": "Keep door and key colors consistent.",
            "narrative": "Name one landmark on the critical path.",
        },
        "generator": "template",
    }
