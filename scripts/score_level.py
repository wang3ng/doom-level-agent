#!/usr/bin/env python3
"""Score a layout JSON against the design rubric."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from critic.scorer import format_score_report, score_layout  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Score a Doom layout JSON")
    p.add_argument(
        "--layout",
        type=Path,
        default=ROOT / "data" / "layouts" / "proto_two_rooms.json",
    )
    p.add_argument(
        "--annotations",
        type=Path,
        help="Optional JSON overrides: {category:{criterion:{score,notes}}}",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Write full JSON report here (default: data/scores/<name>.json)",
    )
    p.add_argument("--quiet", action="store_true", help="JSON only on stdout")
    args = p.parse_args()

    layout = json.loads(args.layout.read_text(encoding="utf-8"))
    annotations = None
    if args.annotations:
        annotations = json.loads(args.annotations.read_text(encoding="utf-8"))

    report = score_layout(layout, annotations=annotations)
    out = args.out
    if out is None:
        name = layout.get("name") or args.layout.stem
        out = ROOT / "data" / "scores" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.quiet:
        print(json.dumps(report, indent=2))
    else:
        print(format_score_report(report))
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
