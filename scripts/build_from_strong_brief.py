#!/usr/bin/env python3
"""Strong-model brief (file) -> Ollama layout JSON -> optional WAD build.

Creative description is authored externally (Cursor / strong LLM) into --brief
or --card. Ollama only compiles geometry JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from critic.scorer import format_score_report, score_layout  # noqa: E402
from path.critical_path import extract_critical_path_from_layout, score_critical_path  # noqa: E402
from pipeline.stage2_layout import brief_to_layout  # noqa: E402
from pipeline.stage3_build import build_map  # noqa: E402
from pipeline.validate import validate_layout  # noqa: E402


def _brief_from_card(card: dict) -> str:
    from pipeline.design_detail import PART_DESIGN_RULES, classic_guidance_for

    theme = str(card.get("theme") or card.get("brief") or card.get("id") or "techbase")
    parts = [
        f"TITLE: {card.get('title') or card.get('id')}",
        f"THEME: {card.get('theme')}",
        f"BRIEF: {card.get('brief')}",
        f"SOLUTION_PATH: {card.get('solution_path')}",
        f"LANDMARKS: {card.get('landmarks')}",
        f"PACING: {card.get('pacing_notes')}",
        f"PART_DESIGNS (honor every entry — shape, elevation, cover, mobs, triggers):\n"
        + json.dumps(
            card.get("part_designs")
            or card.get("layout_constraints", {}).get("room_roles")
            or [],
            indent=2,
        ),
        f"RUBRIC: {json.dumps(card.get('rubric_design') or card.get('rubric_hints') or {}, indent=2)}",
        f"CONSTRAINTS: {json.dumps(card.get('layout_constraints') or {}, indent=2)}",
        PART_DESIGN_RULES,
        classic_guidance_for(theme, k=2),
        "Emit DoomLayoutV0 JSON implementing this design. Keep room ids close to the solution_path names where possible.",
        "Include part_designs, props (cover_block/pillar), and closets when the PART_DESIGNS call for them.",
        "Match classic micro-design denseness: every room needs shape/elevation/cover/mobs/triggers/detail.",
    ]
    return "\n".join(parts)


def _safe_stem(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_").lower() or "layout"


def main() -> int:
    p = argparse.ArgumentParser(description="Brief/card -> Ollama JSON -> WAD")
    p.add_argument("--brief", type=Path, help="Plain-text strong-model brief")
    p.add_argument("--card", type=Path, help="JSON design card from strong describer")
    p.add_argument("--layout-out", type=Path, default=None)
    p.add_argument("--wad-out", type=Path, default=None)
    p.add_argument("--no-build", action="store_true")
    p.add_argument("--no-few-shot", action="store_true")
    p.add_argument("--score", action="store_true")
    args = p.parse_args()

    if args.card:
        card = json.loads(args.card.read_text(encoding="utf-8"))
        brief = _brief_from_card(card)
        stem = _safe_stem(card.get("id") or args.card.stem)
        brief_path = ROOT / "data" / "briefs" / f"{stem}.generated.txt"
        brief_path.write_text(brief, encoding="utf-8")
    elif args.brief:
        brief = args.brief.read_text(encoding="utf-8").strip()
        stem = _safe_stem(args.brief.stem)
    else:
        print("Provide --card or --brief", file=sys.stderr)
        return 2

    print("=== strong brief (input to Ollama) ===")
    print(brief[:1200] + ("..." if len(brief) > 1200 else ""))
    print("=== calling Ollama for layout JSON ===")

    layout = brief_to_layout(brief, use_few_shot=not args.no_few_shot)
    layout["name"] = _safe_stem(str(layout.get("name") or stem))[:64]
    layout["brief"] = layout.get("brief") or brief.split("BRIEF:")[-1].strip()[:500]
    if args.card:
        layout["theme"] = layout.get("theme") or card.get("theme")
        layout.setdefault("objective_room", "exit_bay")

    errors = validate_layout(layout)
    if errors:
        print("validation errors:", errors, file=sys.stderr)

    layout_out = args.layout_out or (ROOT / "data" / "layouts" / f"{layout.get('name', stem)}.json")
    layout_out.parent.mkdir(parents=True, exist_ok=True)
    layout_out.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    print(f"layout: {layout_out}")

    path_report = extract_critical_path_from_layout(layout)
    path_score = score_critical_path(path_report)
    print(f"critical_path_score: {path_score.get('score')} - {path_score.get('notes')}")
    print(f"path_rooms: {path_report.get('path_rooms')}")

    if args.score:
        report = score_layout(layout)
        print(format_score_report(report))
        score_path = ROOT / "data" / "scores" / f"{layout.get('name', stem)}.json"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not args.no_build and not errors:
        wad_out = args.wad_out or (ROOT / "data" / "maps" / f"{layout.get('name', stem)}.wad")
        wad = build_map(layout, wad_out)
        print(f"wad: {wad}")
    elif errors:
        print("skip build due to validation errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
