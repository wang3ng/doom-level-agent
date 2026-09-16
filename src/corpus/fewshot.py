"""Load corpus cards for few-shot layout / brief prompting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = ROOT / "data" / "corpus" / "cards"


def load_cards(cards_dir: Path | None = None) -> list[dict[str, Any]]:
    d = cards_dir or CARDS_DIR
    cards = []
    for p in sorted(d.glob("*.json")):
        try:
            cards.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return cards


def select_few_shot(
    theme_query: str,
    *,
    k: int = 3,
    cards: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Pick up to k cards; prefer theme/brief keyword overlap, else diverse fallback."""
    cards = cards if cards is not None else load_cards()
    q = theme_query.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for c in cards:
        blob = " ".join(
            [
                str(c.get("id", "")),
                str(c.get("theme", "")),
                str(c.get("brief", "")),
            ]
        ).lower()
        score = sum(1 for tok in q.replace(",", " ").split() if tok and tok in blob)
        scored.append((score, c))
    scored.sort(key=lambda t: (-t[0], t[1].get("id", "")))
    picked = [c for s, c in scored if s > 0][:k]
    if len(picked) >= k:
        return picked
    # diversify with remaining cards
    have = {c.get("id") for c in picked}
    for _, c in scored:
        if c.get("id") in have:
            continue
        picked.append(c)
        have.add(c.get("id"))
        if len(picked) >= k:
            break
    return picked


def format_few_shot_block(cards: list[dict[str, Any]]) -> str:
    parts = []
    for i, c in enumerate(cards, 1):
        chunk = [
            f"Example {i} ({c.get('id')} / {c.get('theme')}):",
            f"brief: {c.get('brief')}",
            f"solution_path: {c.get('solution_path')}",
            f"landmarks: {c.get('landmarks')}",
            f"pacing_notes: {c.get('pacing_notes')}",
        ]
        pd = c.get("part_designs") or []
        if pd:
            chunk.append("part_designs:")
            for p in pd[:8]:
                chunk.append(
                    f"  - {p.get('id')}: shape={p.get('shape')}; elev={p.get('elevation')}; "
                    f"cover={p.get('cover')}; mobs={p.get('mobs')}; triggers={p.get('triggers')}; "
                    f"detail={p.get('detail')}"
                )
        parts.append("\n".join(chunk))
    return "\n\n".join(parts)
