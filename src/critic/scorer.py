"""Design rubric scorer for Doom layouts (heuristic + optional annotations/VLM).

Calibration (v0.2): heuristics are intentionally strict.
- Scores 4–5 require human/VLM annotation (or very strong JSON evidence under a hard cap).
- Vision-heavy criteria are capped at HEURISTIC_MAX_VISION.
- Tiny maps take a complexity penalty so a 3-room stub cannot look near-perfect.
- Unscored criteria pull overall_with_gaps down (treated as 1.0).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pipeline.validate import connectivity_ok

ROOT = Path(__file__).resolve().parents[2]
RUBRIC_PATH = ROOT / "configs" / "rubric" / "design_rubric.json"

MONSTERS = {"Zombieman", "ShotgunGuy", "Imp"}
PICKUPS = {"HealthBonus", "Clip", "Shotgun", "ArmorBonus"}
WEAPONS = {"Shotgun"}

# Heuristic ceilings: 4–5 reserved for annotation / VLM.
HEURISTIC_MAX = 3.5
HEURISTIC_MAX_VISION = 2.5
GAP_FILL_SCORE = 1.0  # unscored criteria in overall_with_gaps


@dataclass
class CriterionResult:
    category: str
    criterion: str
    title: str
    score: float | None
    scale_max: float = 5.0
    method: str = "heuristic"  # heuristic | annotation | vlm | unavailable
    confidence: float = 0.0
    notes: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    needs_vision: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_rubric(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or RUBRIC_PATH).read_text(encoding="utf-8"))


def _clamp(x: float, lo: float = 0.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, x))


def _complexity_factor(layout: dict[str, Any]) -> float:
    n = len(layout.get("rooms", []))
    if n <= 1:
        return 0.55
    if n == 2:
        return 0.7
    if n == 3:
        return 0.82
    if n <= 5:
        return 0.92
    return 1.0


def _finalize_heuristic(result: CriterionResult, layout: dict[str, Any]) -> CriterionResult:
    if result.score is None or result.method != "heuristic":
        return result
    cap = HEURISTIC_MAX_VISION if result.needs_vision else HEURISTIC_MAX
    factor = _complexity_factor(layout)
    raw = float(result.score)
    calibrated = _clamp(raw * factor, 0.0, cap)
    note = result.notes
    if calibrated < raw - 0.05:
        note = f"{note} [calibrated: raw {raw:.2f} -> {calibrated:.2f}; cap {cap}; complexity x{factor:.2f}]"
    result.score = round(calibrated, 3)
    result.notes = note
    result.evidence = {
        **result.evidence,
        "raw_score": raw,
        "complexity_factor": factor,
        "heuristic_cap": cap,
    }
    return result


def _room_area(room: dict[str, Any]) -> int:
    return int(room["w"]) * int(room["h"])


def _point_in_room(x: int, y: int, room: dict[str, Any]) -> bool:
    rx, ry, rw, rh = int(room["x"]), int(room["y"]), int(room["w"]), int(room["h"])
    return rx <= x < rx + rw and ry <= y < ry + rh


def _things_by_room(layout: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {r["id"]: [] for r in layout.get("rooms", [])}
    out["_outside"] = []
    for th in layout.get("things", []):
        placed = False
        for room in layout.get("rooms", []):
            if _point_in_room(int(th["x"]), int(th["y"]), room):
                out[room["id"]].append(th)
                placed = True
                break
        if not placed:
            out["_outside"].append(th)
    return out


def _start_room_id(layout: dict[str, Any], by_room: dict[str, list[dict[str, Any]]]) -> str | None:
    for rid, things in by_room.items():
        if rid == "_outside":
            continue
        if any(t.get("type") == "Player1Start" for t in things):
            return rid
    starts = [t for t in layout.get("things", []) if t.get("type") == "Player1Start"]
    if not starts or not layout.get("rooms"):
        return None
    sx, sy = int(starts[0]["x"]), int(starts[0]["y"])
    best = None
    best_d = float("inf")
    for room in layout["rooms"]:
        cx = int(room["x"]) + int(room["w"]) / 2
        cy = int(room["y"]) + int(room["h"]) / 2
        d = (cx - sx) ** 2 + (cy - sy) ** 2
        if d < best_d:
            best_d = d
            best = room["id"]
    return best


def _adj(layout: dict[str, Any]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    graph: dict[str, list[tuple[str, dict[str, Any]]]] = {
        r["id"]: [] for r in layout.get("rooms", [])
    }
    for c in layout.get("connections", []):
        a, b = c["a"], c["b"]
        if a in graph and b in graph:
            graph[a].append((b, c))
            graph[b].append((a, c))
    return graph


def _bfs_order(layout: dict[str, Any], start: str | None) -> list[str]:
    if not start:
        return [r["id"] for r in layout.get("rooms", [])]
    graph = _adj(layout)
    seen = {start}
    order = [start]
    q = [start]
    while q:
        u = q.pop(0)
        for v, _ in graph.get(u, []):
            if v not in seen:
                seen.add(v)
                order.append(v)
                q.append(v)
    for r in layout.get("rooms", []):
        if r["id"] not in seen:
            order.append(r["id"])
    return order


def _unavailable(category: str, criterion: str, title: str, reason: str, needs_vision: bool) -> CriterionResult:
    return CriterionResult(
        category=category,
        criterion=criterion,
        title=title,
        score=None,
        method="unavailable",
        confidence=0.0,
        notes=reason,
        needs_vision=needs_vision,
    )


def score_visual_hierarchy(layout: dict[str, Any]) -> CriterionResult:
    rooms = layout.get("rooms", [])
    lights = [int(r.get("light", 160)) for r in rooms]
    areas = [_room_area(r) for r in rooms]
    light_span = (max(lights) - min(lights)) if lights else 0
    area_span = (max(areas) / max(min(areas), 1)) if areas else 1.0
    score = 0.8
    notes = []
    if light_span >= 40:
        score += 0.7
        notes.append(f"light span {light_span}")
    elif light_span >= 20:
        score += 0.35
        notes.append(f"modest light span {light_span}")
    else:
        notes.append("weak lighting hierarchy")
    if area_span >= 2.0:
        score += 0.5
        notes.append(f"area ratio {area_span:.2f}")
    elif area_span >= 1.4:
        score += 0.25
    if any(t.get("type") == "ExitSwitch" for t in layout.get("things", [])):
        score += 0.4
        notes.append("exit marker")
    else:
        notes.append("no explicit objective landmark in JSON")
    return _finalize_heuristic(
        CriterionResult(
            category="navigation_and_orientation",
            criterion="visual_hierarchy",
            title="Visual Hierarchy",
            score=score,
            method="heuristic",
            confidence=0.35,
            notes="; ".join(notes) + ". Needs screenshots for landmarks/color.",
            evidence={"light_span": light_span, "area_ratio": area_span},
            needs_vision=True,
        ),
        layout,
    )


def score_signposting(layout: dict[str, Any]) -> CriterionResult:
    rooms = layout.get("rooms", [])
    conns = layout.get("connections", [])
    if not connectivity_ok(layout):
        return CriterionResult(
            category="navigation_and_orientation",
            criterion="signposting",
            title="Signposting",
            score=0.5,
            method="heuristic",
            confidence=0.8,
            notes="Room graph is not fully connected.",
            evidence={"connected": False},
            needs_vision=True,
        )
    n, e = len(rooms), len(conns)
    doorish = sum(1 for c in conns if c.get("kind") in {"door", "corridor"})
    score = 1.0
    notes = []
    if e >= n - 1 and n >= 2:
        score += 0.4
        notes.append("connected path exists")
    if doorish:
        score += 0.35
        notes.append(f"{doorish} corridor/door links")
    if n >= 4:
        score += 0.35
        notes.append("enough rooms for route reading")
    else:
        notes.append(f"only {n} rooms; route cues are thin")
    notes.append("no texture/light signifiers in JSON")
    return _finalize_heuristic(
        CriterionResult(
            category="navigation_and_orientation",
            criterion="signposting",
            title="Signposting",
            score=score,
            method="heuristic",
            confidence=0.3,
            notes="; ".join(notes),
            evidence={"edges": e, "rooms": n, "doorish": doorish},
            needs_vision=True,
        ),
        layout,
    )


def score_breadcrumbs(layout: dict[str, Any]) -> CriterionResult:
    by_room = _things_by_room(layout)
    start = _start_room_id(layout, by_room)
    order = _bfs_order(layout, start)
    pickups = [t for t in layout.get("things", []) if t.get("type") in PICKUPS]
    if not pickups:
        return CriterionResult(
            category="navigation_and_orientation",
            criterion="breadcrumbs",
            title="Breadcrumbs",
            score=0.8,
            method="heuristic",
            confidence=0.75,
            notes="No micro-reward pickups along the path.",
            evidence={"pickups": 0},
        )
    rooms_with_pickups = {
        rid
        for rid, things in by_room.items()
        if rid != "_outside" and any(t.get("type") in PICKUPS for t in things)
    }
    spread = len(rooms_with_pickups)
    mid_path = order[1:-1] if len(order) > 2 else order[1:]
    mid_hits = sum(1 for rid in mid_path if rid in rooms_with_pickups)
    score = 1.2 + min(1.2, 0.25 * len(pickups)) + min(0.8, 0.35 * spread)
    if mid_hits:
        score += 0.4
    if start and start in rooms_with_pickups and spread == 1:
        score -= 0.8
        note = "pickups clustered only in start"
    else:
        note = f"pickups in {spread} rooms; mid-path hits={mid_hits}"
    return _finalize_heuristic(
        CriterionResult(
            category="navigation_and_orientation",
            criterion="breadcrumbs",
            title="Breadcrumbs",
            score=score,
            method="heuristic",
            confidence=0.6,
            notes=note,
            evidence={"pickups": len(pickups), "rooms_with_pickups": spread, "mid_hits": mid_hits},
        ),
        layout,
    )


def score_intensity_curve(layout: dict[str, Any]) -> CriterionResult:
    by_room = _things_by_room(layout)
    start = _start_room_id(layout, by_room)
    order = _bfs_order(layout, start)
    densities = []
    for rid in order:
        room = next(r for r in layout["rooms"] if r["id"] == rid)
        m = sum(1 for t in by_room.get(rid, []) if t.get("type") in MONSTERS)
        densities.append(m / max(_room_area(room), 1))
    if not densities:
        return _unavailable("pacing_and_flow", "intensity_curve", "Intensity Curve", "no rooms", False)
    monsters = sum(1 for t in layout.get("things", []) if t.get("type") in MONSTERS)
    if monsters == 0:
        return CriterionResult(
            category="pacing_and_flow",
            criterion="intensity_curve",
            title="Intensity Curve",
            score=1.2,
            method="heuristic",
            confidence=0.55,
            notes="No combat; flat exploration pacing only.",
            evidence={"monsters": 0},
        )
    start_m = sum(1 for t in by_room.get(start or "", []) if t.get("type") in MONSTERS) if start else 0
    peak_at = max(range(len(densities)), key=lambda i: densities[i])
    quiet_rooms = sum(
        1 for rid in order if not any(t.get("type") in MONSTERS for t in by_room.get(rid, []))
    )
    score = 1.2
    notes = []
    if start_m == 0:
        score += 0.6
        notes.append("safe start")
    else:
        notes.append("spawn under fire")
    if peak_at >= max(1, len(order) // 2):
        score += 0.5
        notes.append("later threat peak")
    if quiet_rooms >= 1 and monsters >= 1:
        score += 0.4
        notes.append(f"{quiet_rooms} quiet room(s)")
    if len(order) < 4:
        score -= 0.4
        notes.append("curve is too short to read as a designed arc")
    return _finalize_heuristic(
        CriterionResult(
            category="pacing_and_flow",
            criterion="intensity_curve",
            title="Intensity Curve",
            score=score,
            method="heuristic",
            confidence=0.55,
            notes="; ".join(notes),
            evidence={"densities": densities, "peak_index": peak_at, "start_monsters": start_m},
        ),
        layout,
    )


def score_choke_points_and_arenas(layout: dict[str, Any]) -> CriterionResult:
    rooms = layout.get("rooms", [])
    conns = layout.get("connections", [])
    by_room = _things_by_room(layout)
    if not rooms:
        return _unavailable(
            "pacing_and_flow", "choke_points_and_arenas", "Choke Points and Arenas", "no rooms", False
        )
    areas = [_room_area(r) for r in rooms]
    median = sorted(areas)[len(areas) // 2]
    arenas = [r for r in rooms if _room_area(r) >= median * 1.15]
    chokes = [c for c in conns if int(c.get("width", 64)) <= 96 or c.get("kind") in {"corridor", "door"}]
    combat_arenas = [
        r for r in arenas if any(t.get("type") in MONSTERS for t in by_room.get(r["id"], []))
    ]
    graph = _adj(layout)
    multi = sum(1 for r in combat_arenas if len(graph.get(r["id"], [])) >= 2)
    score = 1.0
    notes = []
    if chokes:
        score += 0.5
        notes.append(f"{len(chokes)} choke link(s)")
    if combat_arenas:
        score += 0.6
        notes.append(f"{len(combat_arenas)} combat arena(s)")
    if multi:
        score += 0.5
        notes.append("multi-approach arena")
    else:
        notes.append("no flanking routes detected")
    props = layout.get("props") or []
    closets = layout.get("closets") or []
    elev_var = len({int(r.get("floor_height", 0)) for r in rooms}) + len(
        {int(r.get("ceiling_height", 128)) for r in rooms}
    )
    if props:
        score += 0.45
        notes.append(f"{len(props)} cover/prop(s)")
    if closets:
        score += 0.35
        notes.append(f"{len(closets)} monster closet(s)")
    if elev_var >= 4:
        score += 0.25
        notes.append("elevation contrast")
    if not props and not closets:
        score -= 0.3
        notes.append("no cover/closet micro-geometry")
    return _finalize_heuristic(
        CriterionResult(
            category="pacing_and_flow",
            criterion="choke_points_and_arenas",
            title="Choke Points and Arenas",
            score=score,
            method="heuristic",
            confidence=0.45,
            notes="; ".join(notes),
            evidence={
                "arena_ids": [r["id"] for r in arenas],
                "chokes": len(chokes),
                "props": len(props),
                "closets": len(closets),
            },
        ),
        layout,
    )


def score_symmetry(layout: dict[str, Any]) -> CriterionResult:
    rooms = layout.get("rooms", [])
    if len(rooms) < 2:
        return CriterionResult(
            category="pacing_and_flow",
            criterion="symmetry_vs_asymmetry",
            title="Symmetry vs. Asymmetry",
            score=1.5,
            method="heuristic",
            confidence=0.25,
            notes="Too few rooms to judge spatial variety.",
            evidence={},
        )
    dims = sorted((int(r["w"]), int(r["h"])) for r in rooms)
    unique = len(set(dims))
    mode = layout.get("mode") or layout.get("play_mode") or "sp"
    # SP: unique footprints are weak evidence only
    score = 1.2 + min(1.0, 0.35 * unique)
    note = f"SP footprint variety {unique}/{len(rooms)} (weak proxy; not MP balance)"
    if str(mode).lower() in {"mp", "multiplayer", "dm"}:
        score = min(score, 2.0)
        note = "MP balance not scored from footprints alone"
    return _finalize_heuristic(
        CriterionResult(
            category="pacing_and_flow",
            criterion="symmetry_vs_asymmetry",
            title="Symmetry vs. Asymmetry",
            score=score,
            method="heuristic",
            confidence=0.25,
            notes=note,
            evidence={"unique_footprints": unique, "mode": mode},
        ),
        layout,
    )


def score_introduction(layout: dict[str, Any]) -> CriterionResult:
    by_room = _things_by_room(layout)
    start = _start_room_id(layout, by_room)
    doors = [
        c
        for c in layout.get("connections", [])
        if c.get("kind") == "door" or c.get("lock") in {"blue", "yellow", "red"}
    ]
    weapons = [t for t in layout.get("things", []) if t.get("type") in WEAPONS]
    keys = [
        t
        for t in layout.get("things", [])
        if t.get("type") in {"BlueCard", "YellowCard", "RedCard"}
    ]
    start_monsters = (
        sum(1 for t in by_room.get(start, []) if t.get("type") in MONSTERS) if start else 0
    )
    score = 1.0
    notes = []
    if weapons:
        score += 0.5
        notes.append("weapon present")
    if doors:
        score += 0.5
        notes.append("door mechanic")
    else:
        notes.append("no door/hazard teach beat beyond combat")
    if keys:
        score += 0.4
        notes.append(f"{len(keys)} key(s)")
    if start_monsters == 0:
        score += 0.5
        notes.append("safe start")
    elif start_monsters > 1:
        score -= 0.4
        notes.append("unsafe intro")
    return _finalize_heuristic(
        CriterionResult(
            category="mechanic_utilization",
            criterion="introduction",
            title="Introduction",
            score=score,
            method="heuristic",
            confidence=0.4,
            notes="; ".join(notes),
            evidence={
                "doors": len(doors),
                "keys": len(keys),
                "weapons": len(weapons),
                "start_monsters": start_monsters,
            },
        ),
        layout,
    )


def score_escalation(layout: dict[str, Any]) -> CriterionResult:
    by_room = _things_by_room(layout)
    start = _start_room_id(layout, by_room)
    order = _bfs_order(layout, start)
    monster_counts = [
        sum(1 for t in by_room.get(rid, []) if t.get("type") in MONSTERS) for rid in order
    ]
    mixed = len({t.get("type") for t in layout.get("things", []) if t.get("type") in MONSTERS})
    total = sum(monster_counts)
    if total == 0:
        return CriterionResult(
            category="mechanic_utilization",
            criterion="escalation",
            title="Escalation",
            score=0.8,
            method="heuristic",
            confidence=0.5,
            notes="no combat escalation",
            evidence={"monster_counts_by_traversal": monster_counts},
        )
    score = 1.0
    notes = []
    if max(monster_counts) > min(monster_counts):
        score += 0.5
        notes.append("uneven monster load")
    if mixed >= 2:
        score += 0.4
        notes.append(f"{mixed} monster types")
    if len(order) >= 4 and monster_counts[-1] >= monster_counts[0]:
        score += 0.4
        notes.append("end harder than start")
    else:
        notes.append("short map; limited escalation ladder")
    return _finalize_heuristic(
        CriterionResult(
            category="mechanic_utilization",
            criterion="escalation",
            title="Escalation",
            score=score,
            method="heuristic",
            confidence=0.4,
            notes="; ".join(notes),
            evidence={"monster_counts_by_traversal": monster_counts, "monster_types": mixed},
        ),
        layout,
    )


def score_subversion(layout: dict[str, Any]) -> CriterionResult:
    return _unavailable(
        "mechanic_utilization",
        "subversion",
        "Subversion",
        "Twist beats need designer annotation or VLM playtrace; not inferred from v0 JSON.",
        needs_vision=True,
    )


def score_readability(layout: dict[str, Any]) -> CriterionResult:
    types = [t.get("type") for t in layout.get("things", [])]
    stock = sum(1 for t in types if t in MONSTERS | PICKUPS | {"Player1Start"})
    unknown = len(types) - stock
    # Stock things are readable, but that is a low bar; keep score modest.
    score = 1.5
    notes = ["stock Doom things only (baseline readability)"]
    if unknown:
        score -= min(1.0, 0.4 * unknown)
        notes.append(f"{unknown} unknown thing type(s)")
    notes.append("hazard/affordance readability needs vision")
    return _finalize_heuristic(
        CriterionResult(
            category="affordance_and_signifiers",
            criterion="readability",
            title="Readability",
            score=score,
            method="heuristic",
            confidence=0.3,
            notes="; ".join(notes),
            evidence={"stock_things": stock, "other_things": unknown},
            needs_vision=True,
        ),
        layout,
    )


def score_consistency(layout: dict[str, Any]) -> CriterionResult:
    by_room = _things_by_room(layout)
    buckets: dict[tuple[Any, ...], list[str]] = {}
    for room in layout.get("rooms", []):
        key = (
            room.get("floor_flat", "FLOOR0_1"),
            room.get("ceil_flat", "CEIL1_1"),
            int(room.get("light", 160)) // 32,
        )
        buckets.setdefault(key, []).append(room["id"])
    contradictions = 0
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        roles = []
        for rid in ids:
            has_m = any(t.get("type") in MONSTERS for t in by_room.get(rid, []))
            roles.append("combat" if has_m else "quiet")
        if "combat" in roles and "quiet" in roles:
            contradictions += 1
    # Absence of contradictions is not excellence on a tiny map.
    score = 2.0 - contradictions * 0.8
    notes = (
        f"{contradictions} look-alike role contradiction(s)"
        if contradictions
        else "no JSON role contradictions (weak positive only)"
    )
    notes += "; invisible walls / climbables need playtest"
    return _finalize_heuristic(
        CriterionResult(
            category="affordance_and_signifiers",
            criterion="consistency",
            title="Consistency",
            score=score,
            method="heuristic",
            confidence=0.35,
            notes=notes,
            evidence={"contradictory_groups": contradictions},
            needs_vision=True,
        ),
        layout,
    )


def score_sense_of_place(layout: dict[str, Any]) -> CriterionResult:
    rooms = layout.get("rooms", [])
    theme = (layout.get("theme") or "").strip()
    lights = [int(r.get("light", 160)) for r in rooms]
    flats = {(r.get("floor_flat"), r.get("ceil_flat")) for r in rooms}
    parts = layout.get("part_designs") or []
    score = 1.0
    notes = []
    if theme:
        score += 0.5
        notes.append(f"theme={theme}")
    if lights and max(lights) - min(lights) >= 40:
        score += 0.4
        notes.append("lighting mood variation")
    if len(flats) >= 2:
        score += 0.3
        notes.append("flat variation")
    if parts:
        score += min(0.6, 0.12 * len(parts))
        notes.append(f"{len(parts)} part_design(s)")
    elif layout.get("props") or layout.get("closets"):
        score += 0.3
        notes.append("micro-geometry present")
    else:
        notes.append("lived-in detail not present in v0 geometry")
    elev = {int(r.get("floor_height", 0)) for r in rooms}
    if len(elev) >= 2:
        score += 0.25
        notes.append("floor elevation contrast")
    return _finalize_heuristic(
        CriterionResult(
            category="narrative_integration",
            criterion="sense_of_place",
            title="Sense of Place",
            score=score,
            method="heuristic",
            confidence=0.4,
            notes="; ".join(notes),
            evidence={"theme": theme, "part_designs": len(parts), "floor_heights": sorted(elev)},
            needs_vision=True,
        ),
        layout,
    )


def score_showing_vs_telling(layout: dict[str, Any]) -> CriterionResult:
    return _unavailable(
        "narrative_integration",
        "showing_vs_telling",
        "Showing vs. Telling",
        "Environmental storytelling needs screenshots/VLM or prop annotations.",
        needs_vision=True,
    )


HEURISTIC_FNS = {
    ("navigation_and_orientation", "visual_hierarchy"): score_visual_hierarchy,
    ("navigation_and_orientation", "signposting"): score_signposting,
    ("navigation_and_orientation", "breadcrumbs"): score_breadcrumbs,
    ("pacing_and_flow", "intensity_curve"): score_intensity_curve,
    ("pacing_and_flow", "choke_points_and_arenas"): score_choke_points_and_arenas,
    ("pacing_and_flow", "symmetry_vs_asymmetry"): score_symmetry,
    ("mechanic_utilization", "introduction"): score_introduction,
    ("mechanic_utilization", "escalation"): score_escalation,
    ("mechanic_utilization", "subversion"): score_subversion,
    ("affordance_and_signifiers", "readability"): score_readability,
    ("affordance_and_signifiers", "consistency"): score_consistency,
    ("narrative_integration", "sense_of_place"): score_sense_of_place,
    ("narrative_integration", "showing_vs_telling"): score_showing_vs_telling,
}


def _apply_annotations(
    results: list[CriterionResult],
    annotations: dict[str, Any] | None,
) -> list[CriterionResult]:
    if not annotations:
        return results
    out = []
    for r in results:
        payload = None
        cat = annotations.get(r.category)
        if isinstance(cat, dict) and r.criterion in cat:
            payload = cat[r.criterion]
        elif r.criterion in annotations:
            payload = annotations[r.criterion]
        if payload is None:
            out.append(r)
            continue
        if isinstance(payload, (int, float)):
            score_v, notes = float(payload), "human/VLM annotation"
            conf = 0.9
        else:
            score_v = float(payload["score"])
            notes = str(payload.get("notes", "human/VLM annotation"))
            conf = float(payload.get("confidence", 0.9))
        out.append(
            CriterionResult(
                category=r.category,
                criterion=r.criterion,
                title=r.title,
                score=_clamp(score_v),
                method="annotation",
                confidence=conf,
                notes=notes,
                evidence=r.evidence,
                needs_vision=r.needs_vision,
            )
        )
    return out


def aggregate(results: list[CriterionResult], rubric: dict[str, Any]) -> dict[str, Any]:
    categories = rubric["categories"]
    by_cat: dict[str, list[CriterionResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    cat_scores = {}
    weighted_sum = 0.0
    weight_total = 0.0
    gap_sum = 0.0
    gap_n = 0
    for cat_id, cat_def in categories.items():
        items = by_cat.get(cat_id, [])
        scored = [r for r in items if r.score is not None]
        w = float(cat_def.get("weight", 1.0))
        if not scored:
            cat_scores[cat_id] = {
                "title": cat_def["title"],
                "score": None,
                "n_scored": 0,
                "n_total": len(items),
                "weight": w,
            }
        else:
            avg = sum(float(r.score) for r in scored) / len(scored)
            cat_scores[cat_id] = {
                "title": cat_def["title"],
                "score": round(avg, 3),
                "n_scored": len(scored),
                "n_total": len(items),
                "weight": w,
            }
            weighted_sum += avg * w
            weight_total += w
        # gap-aware: missing criteria count as GAP_FILL_SCORE
        for r in items:
            gap_n += 1
            gap_sum += float(r.score) if r.score is not None else GAP_FILL_SCORE

    overall = round(weighted_sum / weight_total, 3) if weight_total else None
    overall_with_gaps = round(gap_sum / gap_n, 3) if gap_n else None
    missing = [r.criterion for r in results if r.score is None]
    return {
        "overall": overall,
        "overall_with_gaps": overall_with_gaps,
        "gap_fill_score": GAP_FILL_SCORE,
        "heuristic_max": HEURISTIC_MAX,
        "heuristic_max_vision": HEURISTIC_MAX_VISION,
        "calibration": "v0.2-strict",
        "scale": rubric.get("scale", {"min": 0, "max": 5}),
        "categories": cat_scores,
        "missing_criteria": missing,
        "n_scored": sum(1 for r in results if r.score is not None),
        "n_criteria": len(results),
    }


def score_layout(
    layout: dict[str, Any],
    *,
    annotations: dict[str, Any] | None = None,
    rubric_path: Path | None = None,
) -> dict[str, Any]:
    rubric = load_rubric(rubric_path)
    results: list[CriterionResult] = []
    for cat_id, cat_def in rubric["categories"].items():
        for crit_id, crit_def in cat_def["criteria"].items():
            fn = HEURISTIC_FNS.get((cat_id, crit_id))
            if fn is None:
                results.append(
                    _unavailable(
                        cat_id,
                        crit_id,
                        crit_def["title"],
                        "No scorer implemented.",
                        bool(crit_def.get("needs_vision")),
                    )
                )
            else:
                results.append(fn(layout))
    results = _apply_annotations(results, annotations)
    summary = aggregate(results, rubric)

    # Structural critical-path clarity (room graph), separate from rubric pillars.
    try:
        from path.critical_path import (
            extract_critical_path_from_layout,
            score_critical_path,
        )

        path_report = extract_critical_path_from_layout(layout)
        path_clarity = score_critical_path(path_report)
    except Exception as exc:  # noqa: BLE001
        path_report = {"ok": False, "error": str(exc)}
        path_clarity = {"score": None, "notes": str(exc)}

    return {
        "layout_name": layout.get("name"),
        "rubric_version": rubric.get("version"),
        "summary": summary,
        "criteria": [r.as_dict() for r in results],
        "critical_path": path_report,
        "critical_path_score": path_clarity,
    }


def format_score_report(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"Level score: {s['overall']}/5 scored-only  |  {s.get('overall_with_gaps')}/5 with gaps "
        f"({s['n_scored']}/{s['n_criteria']} criteria; calibration={s.get('calibration')})",
        f"Heuristic caps: {s.get('heuristic_max')} general / {s.get('heuristic_max_vision')} vision-proxy "
        f"(4-5 needs annotation/VLM)",
        "",
    ]
    cp = report.get("critical_path_score") or {}
    if cp.get("score") is not None:
        lines.append(
            f"Critical path clarity: {cp['score']}/5 - {cp.get('notes', '')}"
        )
        lines.append("")
    for cat_id, cat in s["categories"].items():
        val = "n/a" if cat["score"] is None else f"{cat['score']}/5"
        lines.append(f"## {cat['title']}: {val} ({cat['n_scored']}/{cat['n_total']})")
    if s["missing_criteria"]:
        lines.append("")
        lines.append(
            "Unscored (count as "
            f"{s.get('gap_fill_score', 1.0)} in with-gaps): "
            + ", ".join(s["missing_criteria"])
        )
    lines.append("")
    lines.append("Per-criterion:")
    for c in report["criteria"]:
        score = "n/a" if c["score"] is None else f"{c['score']:.2f}"
        lines.append(f"- [{c['method']}] {c['title']}: {score} - {c['notes']}")
    return "\n".join(lines)
