#!/usr/bin/env python3
"""Extract critical path from a WAD or layout JSON, score clarity, describe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from path.critical_path import (  # noqa: E402
    extract_critical_path_from_layout,
    extract_critical_path_from_wad,
    score_critical_path,
)
from path.describe import describe_from_path  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Critical path extract + description")
    p.add_argument("--wad", type=Path, help="Classic Doom PWAD")
    p.add_argument("--layout", type=Path, help="DoomLayoutV0 JSON")
    p.add_argument("--map", dest="map_name", default=None, help="Map lump name")
    p.add_argument("--ollama", action="store_true", help="Ask Ollama for description JSON")
    p.add_argument(
        "--card-out",
        type=Path,
        help="Write/update a corpus card JSON (brief + solution_path)",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Write full analysis JSON (default data/corpus/analysis/<stem>.json)",
    )
    args = p.parse_args()

    if not args.wad and not args.layout:
        print("Provide --wad or --layout", file=sys.stderr)
        return 2

    if args.wad:
        path_report = extract_critical_path_from_wad(args.wad, map_name=args.map_name)
        stem = args.wad.stem.lower()
    else:
        layout = json.loads(args.layout.read_text(encoding="utf-8"))
        path_report = extract_critical_path_from_layout(layout)
        stem = args.layout.stem.lower()

    clarity = score_critical_path(path_report)
    description = describe_from_path(
        path_report, path_score=clarity, offline=not args.ollama
    )

    bundle = {
        "path": path_report,
        "critical_path_score": clarity,
        "description": description,
    }

    out = args.out or (ROOT / "data" / "corpus" / "analysis" / f"{stem}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    if args.card_out:
        card = {
            "id": stem,
            "source_wad": str(args.wad.as_posix()) if args.wad else None,
            "source_layout": str(args.layout.as_posix()) if args.layout else None,
            "theme": description.get("theme"),
            "brief": description.get("brief"),
            "solution_path": description.get("solution_path"),
            "landmarks": description.get("landmarks"),
            "pacing_notes": description.get("pacing_notes"),
            "rubric_hints": description.get("rubric_hints"),
            "critical_path_score": clarity.get("score"),
            "path_meta": {
                "reached_exit": path_report.get("reached_exit"),
                "path_length": path_report.get("path_length"),
                "coverage": path_report.get("coverage"),
                "keys_collected": path_report.get("keys_collected"),
            },
        }
        args.card_out.parent.mkdir(parents=True, exist_ok=True)
        args.card_out.write_text(json.dumps(card, indent=2), encoding="utf-8")
        print(f"card: {args.card_out}")

    print(f"critical_path_score: {clarity.get('score')}/5 - {clarity.get('notes')}")
    print(f"brief: {description.get('brief')}")
    print(f"wrote {out}")
    return 0 if path_report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
