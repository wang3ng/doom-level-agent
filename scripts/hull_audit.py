#!/usr/bin/env python3
"""CLI for hull integrity + walkability gate (see pipeline.hull_gate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.hull_gate import audit_report  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Hull + r=16 walkability audit")
    p.add_argument(
        "maps",
        nargs="*",
        default=["brine_pump_station", "nuclear_plant_v0"],
    )
    p.add_argument("--json", action="store_true", help="Emit JSON report")
    args = p.parse_args()
    total = 0
    for name in args.maps:
        layout = json.loads((ROOT / f"data/layouts/{name}.json").read_text(encoding="utf-8"))
        report = audit_report(layout)
        total += report["n_issues"]
        if args.json:
            print(json.dumps({"name": name, **report}, indent=2))
        else:
            print(f"=== {name} ===")
            for iss in report["issues"]:
                print(f"  {iss['code']} {iss['message']}")
            print(
                f"  {'PASS' if report['ok'] else 'FAIL'} "
                f"({report['n_issues']} issues, r={report['player_radius']})"
            )
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
