#!/usr/bin/env python3
"""Launch a generated PWAD in local UZDoom + Doom2.wad."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / "doom" / "uzdoom.exe"
DEFAULT_IWAD = ROOT / "Doom2.wad"
DEFAULT_MAP = ROOT / "data" / "maps" / "proto_techbase_v1.wad"


def main() -> int:
    p = argparse.ArgumentParser(description="Play a built map in UZDoom")
    p.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    p.add_argument("--iwad", type=Path, default=DEFAULT_IWAD)
    p.add_argument("--file", type=Path, default=DEFAULT_MAP, help="PWAD to load")
    p.add_argument(
        "--smoke",
        action="store_true",
        help="Load map then quit (checks the WAD starts)",
    )
    p.add_argument("extra", nargs="*", help="Extra args passed to UZDoom")
    args = p.parse_args()

    if not args.engine.is_file():
        print(f"Missing engine: {args.engine}", file=sys.stderr)
        return 2
    if not args.iwad.is_file():
        print(f"Missing IWAD: {args.iwad}", file=sys.stderr)
        return 2
    if not args.file.is_file():
        print(f"Missing PWAD: {args.file}", file=sys.stderr)
        return 2

    cmd = [
        str(args.engine),
        "-iwad",
        str(args.iwad),
        "-file",
        str(args.file),
    ]
    if args.smoke:
        # Load MAP01 and exit; useful as a non-interactive start check.
        cmd += ["-nosound", "-nomusic", "+map", "MAP01", "+quit"]
    cmd += args.extra

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
