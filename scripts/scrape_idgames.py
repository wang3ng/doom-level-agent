#!/usr/bin/env python3
"""Scrape idgames file pages (metadata + reviews). Default is fixtures.

Live mode hits the Doomworld frontend (1 req/s). The JSON API is preferred
when unblocked; Cloudflare interstitials fail closed and you should rerun
on william or keep --from-fixtures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from train.idgames import (  # noqa: E402
    SEED_PAGES,
    FileRecord,
    IdgamesBlocked,
    fetch_api_get,
    load_fixture_files,
    scrape_pages,
)


def _dump_files(files: list[FileRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([f.as_dict() for f in files], indent=2),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="HTTP fetch seed pages")
    ap.add_argument("--page", action="append", dest="pages", help="idgames path")
    ap.add_argument("--id", action="append", dest="ids", type=int, help="API file id")
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "train" / "cache" / "idgames_files.json",
    )
    ap.add_argument("--delay", type=float, default=1.2)
    args = ap.parse_args()

    files: list[FileRecord] = []
    if args.live:
        pages = args.pages or SEED_PAGES
        try:
            if args.ids:
                for fid in args.ids:
                    files.append(fetch_api_get(file_id=fid))
            else:
                files = scrape_pages(pages, delay_s=args.delay)
        except IdgamesBlocked as exc:
            print(f"live scrape blocked ({exc}); falling back to fixtures", file=sys.stderr)
            files = load_fixture_files(ROOT / "data" / "train" / "fixtures")
            _dump_files(files, args.out)
            return 2
    else:
        files = load_fixture_files(ROOT / "data" / "train" / "fixtures")

    _dump_files(files, args.out)
    n_rev = sum(len(f.reviews) for f in files)
    print(json.dumps({"n_files": len(files), "n_reviews": n_rev, "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
