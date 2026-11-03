#!/usr/bin/env python3
"""Build the JSONL SFT pack from verified layouts + idgames comment fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from train.pack import build_pack, write_pack  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build DoomLayoutV0 SFT JSONL")
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "train" / "sft.jsonl",
    )
    ap.add_argument("--no-verified", action="store_true")
    ap.add_argument("--no-community", action="store_true")
    ap.add_argument(
        "--fixtures",
        type=Path,
        default=ROOT / "data" / "train" / "fixtures",
    )
    args = ap.parse_args()
    records = build_pack(
        root=ROOT,
        fixtures_dir=args.fixtures,
        include_verified=not args.no_verified,
        include_community=not args.no_community,
    )
    stats = write_pack(records, jsonl_path=args.out)
    print(json.dumps(stats, indent=2))
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
