"""Layout validation against JSON Schema + simple playability checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "configs" / "schema" / "layout.schema.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_layout(layout: dict[str, Any]) -> list[str]:
    """Return a list of error strings (empty if OK)."""
    errors: list[str] = []
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(load_schema())
        for e in sorted(validator.iter_errors(layout), key=lambda x: list(x.path)):
            errors.append(e.message)
    else:
        for key in ("name", "rooms", "connections", "things"):
            if key not in layout:
                errors.append(f"missing required key: {key}")

    room_ids = {r.get("id") for r in layout.get("rooms", [])}
    if len(room_ids) != len(layout.get("rooms", [])):
        errors.append("duplicate room ids")

    for c in layout.get("connections", []):
        if c.get("a") not in room_ids or c.get("b") not in room_ids:
            errors.append(f"connection references unknown room: {c}")

    starts = [t for t in layout.get("things", []) if t.get("type") == "Player1Start"]
    if len(starts) != 1:
        errors.append(f"expected exactly one Player1Start, found {len(starts)}")

    key_colors = {
        "BlueCard": "blue",
        "YellowCard": "yellow",
        "RedCard": "red",
    }
    present = {
        key_colors[t["type"]]
        for t in layout.get("things", [])
        if t.get("type") in key_colors
    }
    for c in layout.get("connections", []):
        lock = c.get("lock")
        if lock and lock not in present:
            errors.append(f"connection {c.get('a')}->{c.get('b')} locks with {lock} but no matching key thing")

    return errors


def connectivity_ok(layout: dict[str, Any]) -> bool:
    """Undirected BFS over room connection graph."""
    rooms = [r["id"] for r in layout.get("rooms", [])]
    if not rooms:
        return False
    adj: dict[str, set[str]] = {r: set() for r in rooms}
    for c in layout.get("connections", []):
        a, b = c["a"], c["b"]
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    start = rooms[0]
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return len(seen) == len(rooms)
