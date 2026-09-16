"""Classic Doom level design references for detailed brief generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CLASSIC_DIR = ROOT / "data" / "corpus" / "classic"


def load_classic_refs(classic_dir: Path | None = None) -> list[dict[str, Any]]:
    d = classic_dir or CLASSIC_DIR
    if not d.is_dir():
        return []
    refs: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            refs.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return refs


def load_primer(classic_dir: Path | None = None) -> dict[str, Any] | None:
    path = (classic_dir or CLASSIC_DIR) / "design_primer.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def select_classic_refs(
    theme_query: str,
    *,
    k: int = 2,
    refs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Pick classic map refs (excluding the primer) by theme overlap."""
    refs = [r for r in (refs if refs is not None else load_classic_refs()) if r.get("id") != "classic_design_primer"]
    q = theme_query.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for r in refs:
        blob = " ".join(
            [
                str(r.get("id", "")),
                str(r.get("theme", "")),
                str(r.get("title", "")),
                str(r.get("brief", "")),
                " ".join(r.get("design_lessons") or []),
            ]
        ).lower()
        score = sum(1 for tok in q.replace(",", " ").split() if len(tok) > 2 and tok in blob)
        # slight prior for iconic teach maps when query is generic
        if "entry" in q or "tutorial" in q or "teach" in q:
            if "entryway" in str(r.get("id", "")):
                score += 3
        if "tech" in q or "plant" in q or "nukage" in q:
            if "nuclear" in str(r.get("id", "")):
                score += 3
        if "hell" in q or "inferno" in q or "flesh" in q:
            if "house_of_pain" in str(r.get("id", "")):
                score += 3
        scored.append((score, r))
    scored.sort(key=lambda t: (-t[0], t[1].get("id", "")))
    picked = [r for s, r in scored if s > 0][:k]
    if len(picked) >= k:
        return picked
    have = {r.get("id") for r in picked}
    for _, r in scored:
        if r.get("id") in have:
            continue
        picked.append(r)
        if len(picked) >= k:
            break
    return picked


def format_part_designs(parts: list[dict[str, Any]], *, limit: int | None = None) -> str:
    lines: list[str] = []
    for i, p in enumerate(parts if limit is None else parts[:limit]):
        lines.append(
            f"  - [{p.get('id')}] role={p.get('role')}; shape={p.get('shape')}; "
            f"elevation={p.get('elevation')}; cover={p.get('cover')}; "
            f"mobs={p.get('mobs')}; triggers={p.get('triggers')}"
        )
        if p.get("light"):
            lines.append(f"    light: {p.get('light')}")
        if p.get("textures"):
            lines.append(f"    textures: {p.get('textures')}")
        if p.get("detail"):
            lines.append(f"    detail: {p.get('detail')}")
    return "\n".join(lines)


def format_classic_ref(ref: dict[str, Any], *, max_parts: int = 8) -> str:
    parts = ref.get("part_designs") or []
    lessons = ref.get("design_lessons") or []
    block = [
        f"CLASSIC REF: {ref.get('title')} ({ref.get('source')})",
        f"theme: {ref.get('theme')}",
        f"brief: {ref.get('brief')}",
        f"solution_path: {ref.get('solution_path')}",
        f"landmarks: {ref.get('landmarks')}",
        f"pacing: {ref.get('pacing_notes')}",
        "part_designs:",
        format_part_designs(parts, limit=max_parts),
    ]
    if lessons:
        block.append("lessons: " + "; ".join(lessons))
    return "\n".join(block)


def format_primer_block(primer: dict[str, Any] | None = None) -> str:
    primer = primer if primer is not None else load_primer()
    if not primer:
        return ""
    rules = primer.get("global_rules") or []
    anti = primer.get("anti_patterns") or []
    contrasts = primer.get("contrast_pairs") or []
    fields = primer.get("part_fields") or {}
    lines = [
        "CLASSIC DOOM DESIGN PRIMER:",
        "Global rules:",
        *[f"- {r}" for r in rules],
        "part_design fields: " + ", ".join(f"{k}={v}" for k, v in fields.items()),
        "Useful contrasts: " + "; ".join(contrasts),
        "Anti-patterns to avoid:",
        *[f"- {a}" for a in anti],
    ]
    return "\n".join(lines)


def format_classic_block(
    theme_query: str,
    *,
    k: int = 2,
    include_primer: bool = True,
    max_parts: int = 8,
) -> str:
    chunks: list[str] = []
    if include_primer:
        primer = format_primer_block()
        if primer:
            chunks.append(primer)
    for ref in select_classic_refs(theme_query, k=k):
        chunks.append(format_classic_ref(ref, max_parts=max_parts))
    return "\n\n".join(chunks)
