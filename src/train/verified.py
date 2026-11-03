"""SFT examples from hull-gated layouts, corpus cards, and classic refs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .sft import BRIEF_TASK, LAYOUT_TASK, REPAIR_TASK, ChatRecord, dumps_json

ROOT = Path(__file__).resolve().parents[2]


def _stage2_system() -> str:
    from pipeline.stage2_layout import SYSTEM

    return SYSTEM


def _brief_system() -> str:
    from path.describe import SYSTEM

    return SYSTEM


def load_passing_layouts(root: Path | None = None) -> list[tuple[str, dict[str, Any]]]:
    root = root or ROOT
    from pipeline.hull_gate import audit_report
    from pipeline.validate import connectivity_ok, validate_layout

    out: list[tuple[str, dict[str, Any]]] = []
    for path in sorted((root / "data" / "layouts").glob("*.json")):
        layout = json.loads(path.read_text(encoding="utf-8"))
        if validate_layout(layout):
            continue
        if not connectivity_ok(layout):
            continue
        if not audit_report(layout)["ok"]:
            continue
        out.append((path.stem, layout))
    return out


def _layout_users(layout: dict[str, Any]) -> list[str]:
    brief = layout.get("brief") or layout.get("name") or "a small techbase"
    theme = layout.get("theme") or ""
    return [
        (
            "Design a small playable Doom layout for this brief:\n"
            f"{brief}\n"
            "Return JSON only. Every room must have a matching part_designs entry."
        ),
        (
            "Fill DoomLayoutV0 JSON that realizes this brief. "
            "Honor hub-return, measurable part_designs, and landmarks ≥64–96u off portal axes.\n"
            f"Theme: {theme}\nBrief:\n{brief}\nReturn JSON only."
        ),
    ]


def _repair_user(layout: dict[str, Any]) -> str | None:
    props = layout.get("props") or []
    pillar = next((p for p in props if p.get("type") == "pillar"), None)
    if not pillar:
        return None
    brief = layout.get("brief") or layout.get("name")
    return (
        "Playtest: the hub pillar read as a corridor dead-end (sightline blocked). "
        "Move the landmark off every portal approach axis; keep it in the hub as cover.\n"
        f"Target room: {pillar.get('in_room')}. "
        f"Correct pillar origin should be ({pillar.get('x')}, {pillar.get('y')}) "
        f"size {pillar.get('w')}x{pillar.get('h')}.\n"
        f"Brief:\n{brief}\n"
        "Return the full corrected layout JSON."
    )


def _part_design_user(layout: dict[str, Any]) -> str:
    rooms = [
        {
            "id": r.get("id"),
            "w": r.get("w"),
            "h": r.get("h"),
            "shape": r.get("shape"),
            "light": r.get("light"),
        }
        for r in layout.get("rooms") or []
    ]
    return (
        "Write part_designs for this geometry. Measurable shape/light/cover; "
        "do not move rooms.\n"
        f"brief: {layout.get('brief')}\n"
        f"rooms: {dumps_json(rooms)}\n"
        "Return JSON {\"part_designs\": [...]} only."
    )


def layout_records(name: str, layout: dict[str, Any]) -> list[ChatRecord]:
    system = _stage2_system()
    body = dumps_json(layout)
    rows: list[ChatRecord] = []
    for i, user in enumerate(_layout_users(layout)):
        rows.append(
            ChatRecord(
                id=f"verified:{name}:layout:{i}",
                source="verified",
                task=LAYOUT_TASK,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": body},
                ],
                meta={"layout": name, "n_rooms": len(layout.get("rooms") or [])},
            )
        )
    repair = _repair_user(layout)
    if repair:
        rows.append(
            ChatRecord(
                id=f"verified:{name}:repair:pillar",
                source="verified",
                task=REPAIR_TASK,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": repair},
                    {"role": "assistant", "content": body},
                ],
                meta={"layout": name, "fix": "hub_pillar_off_axis"},
            )
        )
    parts = layout.get("part_designs") or []
    if parts:
        rows.append(
            ChatRecord(
                id=f"verified:{name}:part_designs",
                source="verified",
                task=LAYOUT_TASK,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": _part_design_user(layout)},
                    {
                        "role": "assistant",
                        "content": dumps_json({"part_designs": parts}),
                    },
                ],
                meta={"layout": name},
            )
        )
    return rows


def classic_part_records(root: Path | None = None) -> list[ChatRecord]:
    root = root or ROOT
    system = _stage2_system()
    rows: list[ChatRecord] = []
    classic_dir = root / "data" / "corpus" / "classic"
    layouts = {n: lay for n, lay in load_passing_layouts(root)}
    pairs = [
        ("nuclear_plant.json", "nuclear_plant_v0"),
        ("hangar.json", "proto_techbase_v1"),
    ]
    for classic_name, layout_name in pairs:
        cpath = classic_dir / classic_name
        if not cpath.is_file() or layout_name not in layouts:
            continue
        classic = json.loads(cpath.read_text(encoding="utf-8"))
        layout = layouts[layout_name]
        user = (
            "Imitate the CLASSIC DOOM micro-design depth below "
            "(do NOT copy room ids; invent a new map that fits this brief):\n"
            f"{dumps_json({'title': classic.get('title'), 'brief': classic.get('brief'), 'part_designs': classic.get('part_designs', [])[:6]})}\n"
            f"Brief to realize:\n{layout.get('brief')}\n"
            "Return JSON only."
        )
        rows.append(
            ChatRecord(
                id=f"verified:classic:{layout_name}",
                source="verified",
                task=LAYOUT_TASK,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": dumps_json(layout)},
                ],
                meta={"layout": layout_name, "classic": classic.get("id")},
            )
        )
    return rows


def card_brief_records(root: Path | None = None) -> list[ChatRecord]:
    root = root or ROOT
    system = _brief_system()
    rows: list[ChatRecord] = []
    cards_dir = root / "data" / "corpus" / "cards"
    for path in sorted(cards_dir.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        if not card.get("brief"):
            continue
        analysis = {
            "id": card.get("id"),
            "theme": card.get("theme"),
            "solution_path": card.get("solution_path"),
            "landmarks": card.get("landmarks"),
            "pacing_notes": card.get("pacing_notes"),
            "path_meta": card.get("path_meta") or card.get("critical_path_score"),
        }
        target = {
            "theme": card.get("theme"),
            "brief": card.get("brief"),
            "solution_path": card.get("solution_path"),
            "landmarks": card.get("landmarks"),
            "pacing_notes": card.get("pacing_notes"),
            "part_designs": card.get("part_designs") or [],
            "rubric_hints": card.get("rubric_hints") or card.get("rubric_design") or {},
        }
        rows.append(
            ChatRecord(
                id=f"verified:card:{path.stem}:brief",
                source="verified",
                task=BRIEF_TASK,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": (
                            "Write a Doom level brief from this critical-path analysis. JSON only.\n"
                            + dumps_json(analysis)
                        ),
                    },
                    {"role": "assistant", "content": dumps_json(target)},
                ],
                meta={"card": path.stem},
            )
        )
    return rows


def build_verified_records(root: Path | None = None) -> list[ChatRecord]:
    root = root or ROOT
    rows: list[ChatRecord] = []
    for name, layout in load_passing_layouts(root):
        rows.extend(layout_records(name, layout))
    rows.extend(classic_part_records(root))
    rows.extend(card_brief_records(root))
    return rows
