#!/usr/bin/env python3
"""Run prototype pipeline: optional LLM layout, always JSON->UDMF WAD."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from critic.metrics import summarize  # noqa: E402
from critic.scorer import format_score_report, score_layout  # noqa: E402
from pipeline.stage1_image import generate_concept_image  # noqa: E402
from pipeline.stage2_layout import brief_to_layout  # noqa: E402
from pipeline.stage3_build import build_map  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Doom level agent prototype")
    p.add_argument("--brief", type=Path, help="Text brief file")
    p.add_argument("--layout", type=Path, help="Existing layout JSON (skip LLM)")
    p.add_argument("--out", type=Path, default=ROOT / "data" / "maps" / "MAP01.wad")
    p.add_argument("--ollama", action="store_true", help="Call Ollama for stage 2")
    p.add_argument("--concept", action="store_true", help="Write stage-1 concept stub")
    p.add_argument("--score", action="store_true", help="Run design rubric scorer")
    args = p.parse_args()

    if args.layout:
        layout = json.loads(args.layout.read_text(encoding="utf-8"))
    elif args.brief and args.ollama:
        brief = args.brief.read_text(encoding="utf-8").strip()
        if args.concept:
            img = generate_concept_image(brief, ROOT / "data" / "screenshots" / "concept.svg")
            print(f"concept stub: {img}")
        layout = brief_to_layout(brief)
        layout_path = ROOT / "data" / "layouts" / f"{layout.get('name', 'generated')}.json"
        layout_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
        print(f"layout json: {layout_path}")
    elif args.brief:
        print("Provide --layout or --ollama with --brief", file=sys.stderr)
        return 2
    else:
        layout = json.loads(
            (ROOT / "data" / "layouts" / "proto_two_rooms.json").read_text(encoding="utf-8")
        )

    print("metrics:", json.dumps(summarize(layout), indent=2))
    if args.score:
        report = score_layout(layout)
        print(format_score_report(report))
        score_path = ROOT / "data" / "scores" / f"{layout.get('name', 'layout')}.json"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        score_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"score report: {score_path}")
    wad = build_map(layout, args.out)
    print(f"wrote {wad}")
    print(f"udmf text: {wad.with_suffix('.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
