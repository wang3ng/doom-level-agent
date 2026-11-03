"""Merge verified + community records into one JSONL pack + lessons sidecar."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .comments import lessons_from_records, records_from_file
from .idgames import FileRecord, load_fixture_files
from .sft import ChatRecord, dump_jsonl
from .verified import ROOT, build_verified_records


def community_records(
    *,
    fixtures_dir: Path | None = None,
    files: list[FileRecord] | None = None,
) -> list[ChatRecord]:
    if files is None:
        fixtures_dir = fixtures_dir or (ROOT / "data" / "train" / "fixtures")
        files = load_fixture_files(fixtures_dir)
    rows: list[ChatRecord] = []
    for rec in files:
        rows.extend(records_from_file(rec))
    return rows


def build_pack(
    *,
    root: Path | None = None,
    fixtures_dir: Path | None = None,
    files: list[FileRecord] | None = None,
    include_verified: bool = True,
    include_community: bool = True,
) -> list[ChatRecord]:
    root = root or ROOT
    rows: list[ChatRecord] = []
    if include_verified:
        rows.extend(build_verified_records(root))
    if include_community:
        rows.extend(
            community_records(
                fixtures_dir=fixtures_dir or (root / "data" / "train" / "fixtures"),
                files=files,
            )
        )
    return rows


def pack_stats(records: list[ChatRecord]) -> dict[str, Any]:
    by_source = Counter(r.source for r in records)
    by_task = Counter(r.task for r in records)
    return {
        "n": len(records),
        "by_source": dict(by_source),
        "by_task": dict(by_task),
        "n_lessons": len(lessons_from_records(records)),
    }


def write_pack(
    records: list[ChatRecord],
    *,
    jsonl_path: Path,
    lessons_path: Path | None = None,
    stats_path: Path | None = None,
) -> dict[str, Any]:
    dump_jsonl(records, jsonl_path)
    lessons = lessons_from_records(records)
    if lessons_path is None:
        lessons_path = jsonl_path.with_name("community_lessons.json")
    lessons_path.write_text(json.dumps(lessons, indent=2), encoding="utf-8")
    stats = pack_stats(records)
    stats["jsonl"] = str(jsonl_path)
    stats["lessons"] = str(lessons_path)
    if stats_path is None:
        stats_path = jsonl_path.with_name("sft_stats.json")
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats
