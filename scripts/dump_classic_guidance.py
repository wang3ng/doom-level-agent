#!/usr/bin/env python3
"""Print classic Doom design guidance for strong-describer / planner prompts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corpus.classic import format_classic_block, load_classic_refs  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Dump classic Doom design refs")
    p.add_argument("--theme", default="techbase plant hub key nukage", help="theme query for matching")
    p.add_argument("--k", type=int, default=3, help="number of classic maps to include")
    p.add_argument("--list", action="store_true", help="list available classic ref ids")
    p.add_argument("--out", type=Path, default=None, help="optional write path")
    args = p.parse_args()

    if args.list:
        for r in load_classic_refs():
            print(f"{r.get('id')}: {r.get('title') or r.get('id')}")
        return 0

    text = format_classic_block(args.theme, k=args.k, include_primer=True, max_parts=12)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
