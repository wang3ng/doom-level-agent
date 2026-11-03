"""Chat SFT records (Ollama / OpenAI messages JSONL)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

LAYOUT_TASK = "layout"
CRITIC_TASK = "critic"
BRIEF_TASK = "brief"
REPAIR_TASK = "repair"


@dataclass
class ChatRecord:
    id: str
    source: str
    task: str
    messages: list[dict[str, str]]
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def dump_jsonl(records: list[ChatRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.as_dict(), ensure_ascii=False) + "\n")
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
