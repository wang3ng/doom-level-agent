"""Automatic playability / density metrics (no VLM yet)."""

from __future__ import annotations

from typing import Any

from pipeline.validate import connectivity_ok


def summarize(layout: dict[str, Any]) -> dict[str, Any]:
    rooms = layout.get("rooms", [])
    things = layout.get("things", [])
    area = sum(int(r["w"]) * int(r["h"]) for r in rooms)
    monsters = [
        t
        for t in things
        if t.get("type") in {"Zombieman", "ShotgunGuy", "Imp"}
    ]
    return {
        "num_rooms": len(rooms),
        "num_connections": len(layout.get("connections", [])),
        "connected": connectivity_ok(layout),
        "area_map_units2": area,
        "num_monsters": len(monsters),
        "monster_density_per_1e6": (len(monsters) / area * 1_000_000) if area else 0.0,
        "has_player_start": any(t.get("type") == "Player1Start" for t in things),
    }
