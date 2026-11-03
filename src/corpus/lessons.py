"""Player-comment lessons for Stage 2 prompts (from the training pack)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LESSONS_PATH = ROOT / "data" / "train" / "community_lessons.json"


def load_lessons(path: Path | None = None) -> list[str]:
    p = path or LESSONS_PATH
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(x) for x in data if str(x).strip()]
    return []


def select_lessons(theme_query: str, *, k: int = 4, lessons: list[str] | None = None) -> list[str]:
    lessons = lessons if lessons is not None else load_lessons()
    if not lessons:
        return []
    q = theme_query.lower()
    scored: list[tuple[int, str]] = []
    for lesson in lessons:
        blob = lesson.lower()
        score = sum(1 for tok in q.replace(",", " ").split() if tok and tok in blob)
        scored.append((score, lesson))
    scored.sort(key=lambda t: (-t[0], t[1]))
    picked = [s for sc, s in scored if sc > 0][:k]
    if len(picked) >= k:
        return picked
    have = set(picked)
    for _, lesson in scored:
        if lesson in have:
            continue
        picked.append(lesson)
        have.add(lesson)
        if len(picked) >= k:
            break
    return picked


def format_lessons_block(theme_query: str, *, k: int = 4) -> str:
    items = select_lessons(theme_query, k=k)
    if not items:
        return ""
    return "\n".join(f"- {x}" for x in items)
