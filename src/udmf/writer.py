"""Deterministic JSON layout -> UDMF TEXTMAP (+ minimal PWAD).

Builds axis-aligned room sectors and inserts corridor sectors for each
connection so the map is walkable in GZDoom / editable in UDB.
"""

from __future__ import annotations

import copy
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

THING_ED_NUMBERS = {
    "Player1Start": 1,
    "Zombieman": 3004,
    "ShotgunGuy": 9,
    "Imp": 3001,
    "HealthBonus": 2014,
    "Clip": 2007,
    "Shotgun": 2001,
    "ArmorBonus": 2015,
    "BlueCard": 5,
    "YellowCard": 6,
    "RedCard": 13,
    # ExitSwitch is a layout marker only — becomes linedef special Exit_Normal.
}

KEY_COLOR = {
    "BlueCard": "blue",
    "YellowCard": "yellow",
    "RedCard": "red",
}

DEFAULT_WALL = "STARTAN2"
DEFAULT_OPEN = "-"  # no midtex on passable two-sided lines
EXIT_SWITCH_TEX = "SW1EXIT"
DOOR_FACE_TEX = "BIGDOOR2"
DOOR_TRACK_TEX = "DOORTRAK"
# Classic Doom step/riser textures for floor elevation changes
STEP_TEX = "STEP2"
STEPTOP_TEX = "STEPTOP"
# ZDoom UDMF action specials (namespace zdoom)
EXIT_NORMAL_SPECIAL = 243
DOOR_RAISE_SPECIAL = 12
DOOR_LOCKED_RAISE_SPECIAL = 13
DOOR_OPEN_SPECIAL = 11  # closet release (stays open)
# ZDoom plat lift (walk-on temporary elevator)
# 62 = Plat_DownWaitUpStay (default 8-unit lip — looks broken)
# 206 = Plat_DownWaitUpStayLip (tag, speed, delay, lip)
PLAT_DOWN_WAIT_UP_STAY_LIP = 206
SUPPORT_TEX = "SUPPORT3"
METAL_TEX = "METAL"
# Standard Doom LOCKDEFS card locks
LOCK_NUMBERS = {"red": 1, "blue": 2, "yellow": 3}


def _point_in_room(x: int, y: int, room: dict[str, Any]) -> bool:
    """True if (x,y) is inside the room polygon (rect or L), not just AABB."""
    rx, ry = int(room["x"]), int(room["y"])
    w, h = int(room["w"]), int(room["h"])
    if rx <= x < rx + w and ry <= y < ry + h:
        return True
    if room.get("shape") != "L":
        return False
    side = room.get("wing_side", "east")
    ww = int(room.get("wing_w", max(96, w // 2)))
    wh = int(room.get("wing_h", max(96, h // 2)))
    if side == "east":
        return rx + w <= x < rx + w + ww and ry <= y < ry + wh
    if side == "west":
        return rx - ww <= x < rx and ry <= y < ry + wh
    if side == "north":
        return rx <= x < rx + ww and ry + h <= y < ry + h + wh
    return rx <= x < rx + ww and ry - wh <= y < ry


def _exit_anchors(layout: dict[str, Any], rooms: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    """Return (x, y, sector_hint_or_-1) markers for exit switches."""
    anchors: list[tuple[int, int, int]] = []
    id_to_room = {r["id"]: r for r in rooms if not r.get("_synthetic")}

    for th in layout.get("things", []):
        if th.get("type") != "ExitSwitch":
            continue
        x, y = int(th["x"]), int(th["y"])
        sid = -1
        for i, room in enumerate(rooms):
            if room.get("_synthetic"):
                continue
            if _point_in_room(x, y, room):
                # sector index is assigned in layout order of all rooms; resolved later
                sid = i
                break
        anchors.append((x, y, sid))

    if anchors:
        return anchors

    obj = layout.get("objective_room")
    if obj and obj in id_to_room:
        r = id_to_room[obj]
        x0, y0, x1, y1 = _room_bounds(r)
        # Prefer far wall of the exit room (right edge center by default).
        anchors.append(((x0 + x1) // 2, y1 - 16, -1))
    return anchors


def _apply_exit_linedefs(
    *,
    layout: dict[str, Any],
    rooms: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    vertices: list[Vertex],
    linedefs: list[dict[str, Any]],
    sidedefs: list[dict[str, Any]],
) -> int:
    """Turn ExitSwitch / objective_room into usable Exit_Normal linedefs. Returns count."""
    anchors = _exit_anchors(layout, rooms)
    if not anchors:
        return 0

    applied = 0
    used: set[int] = set()
    for ax, ay, _ in anchors:
        # Resolve target sector from room containing the anchor.
        target_sid: int | None = None
        for room in rooms:
            if room.get("_synthetic"):
                continue
            if _point_in_room(ax, ay, room):
                target_sid = id_to_sector[room["id"]]
                break
        if target_sid is None and layout.get("objective_room") in id_to_sector:
            target_sid = id_to_sector[layout["objective_room"]]
        if target_sid is None:
            continue

        best_i: int | None = None
        best_dist = 10**18
        for i, ld in enumerate(linedefs):
            if i in used or not ld.get("blocking") or ld.get("twosided"):
                continue
            if sidedefs[ld["sidefront"]]["sector"] != target_sid:
                continue
            v1, v2 = vertices[ld["v1"]], vertices[ld["v2"]]
            mx, my = (v1.x + v2.x) / 2.0, (v1.y + v2.y) / 2.0
            dist = (mx - ax) ** 2 + (my - ay) ** 2
            if dist < best_dist:
                best_dist = dist
                best_i = i

        if best_i is None:
            continue

        ld = linedefs[best_i]
        ld["special"] = EXIT_NORMAL_SPECIAL
        ld["playeruse"] = True
        sd = sidedefs[ld["sidefront"]]
        sd["texturemiddle"] = EXIT_SWITCH_TEX
        used.add(best_i)
        applied += 1

    return applied


def _apply_door_linedefs(
    *,
    rooms: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    sectors: list[Sector],
    linedefs: list[dict[str, Any]],
    sidedefs: list[dict[str, Any]],
) -> int:
    """Attach Door_Raise / Door_LockedRaise to portals into door corridors.

    Monster-closet doors are textured here but opened by a separate walk
    tripwire (_apply_closet_tripwires) — playercross on the closed door face
    never fires because the player cannot cross a zero-height door sector.
    """
    applied = 0
    for room in rooms:
        if not room.get("_door"):
            continue
        door_sid = id_to_sector[room["id"]]
        tag = int(room["_door_tag"])
        lock = room.get("_lock")
        sectors[door_sid].tag = tag
        sectors[door_sid].wall_texture = DOOR_TRACK_TEX

        for ld in linedefs:
            if not ld.get("twosided") or "sideback" not in ld:
                continue
            sf = sidedefs[ld["sidefront"]]["sector"]
            sb = sidedefs[ld["sideback"]]["sector"]
            if door_sid not in (sf, sb) or sf == sb:
                continue
            if "special" in ld:
                continue

            # Door faces: upper only (BIGDOOR), never midtex (midtex hides open doors).
            for sdi in (ld["sidefront"], ld["sideback"]):
                sidedefs[sdi]["texturemiddle"] = DEFAULT_OPEN
            face_sd = ld["sidefront"] if sf != door_sid else ld["sideback"]
            sidedefs[face_sd]["texturetop"] = DOOR_FACE_TEX
            # Inside of door sector: blank uppers (door track is on one-sided walls).
            door_sd = ld["sideback"] if face_sd == ld["sidefront"] else ld["sidefront"]
            sidedefs[door_sd]["texturetop"] = DEFAULT_OPEN
            # Preserve / restore lower (step) textures when neighboring floors differ.
            # Blanking bottoms caused HOM/black void on height-mismatched door portals
            # (e.g. hub floor 0 <-> arena floor 16 through yellow lock).
            door_floor = sectors[door_sid].floor_height
            other_sid = sb if sf == door_sid else sf
            other_floor = sectors[other_sid].floor_height
            if door_floor < other_floor:
                delta = other_floor - door_floor
                sidedefs[door_sd]["texturebottom"] = (
                    STEPTOP_TEX if delta >= 48 else STEP_TEX
                )
            else:
                sidedefs[door_sd]["texturebottom"] = DEFAULT_OPEN
            if other_floor < door_floor:
                delta = door_floor - other_floor
                sidedefs[face_sd]["texturebottom"] = (
                    STEPTOP_TEX if delta >= 48 else STEP_TEX
                )

            if room.get("_closet_release"):
                # Special lives on the tripwire, not on these faces.
                applied += 1
                continue

            if lock in LOCK_NUMBERS:
                ld["special"] = DOOR_LOCKED_RAISE_SPECIAL
                ld["arg0"] = tag
                ld["arg1"] = 16
                ld["arg2"] = 150
                ld["arg3"] = LOCK_NUMBERS[lock]
                ld["playeruse"] = True
                ld["repeatspecial"] = True
            else:
                ld["special"] = DOOR_RAISE_SPECIAL
                ld["arg0"] = tag
                ld["arg1"] = 16
                ld["arg2"] = 150
                ld["playeruse"] = True
                ld["repeatspecial"] = True
            applied += 1

    return applied


def _apply_closet_tripwires(
    *,
    rooms: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    vertices: list[Vertex],
    vindex: dict[tuple[int, int], int],
    sidedefs: list[dict[str, Any]],
    linedefs: list[dict[str, Any]],
) -> int:
    """Walk-over lines inside the parent room that Door_Open the closet tag."""
    room_by_id = {r["id"]: r for r in rooms}
    applied = 0
    for door in rooms:
        if not door.get("_closet_release"):
            continue
        parent_id = door.get("_closet_parent")
        parent = room_by_id.get(parent_id)
        if not parent or parent_id not in id_to_sector:
            continue
        parent_sid = id_to_sector[parent_id]
        tag = int(door["_door_tag"])
        dx0, dy0, dx1, dy1 = _room_bounds(door)
        inset = 24

        # Orient so player walking toward the closet crosses front -> back.
        if door.get("_portal_left") == parent_id:
            # Door east of parent: vertical tripwire, front faces west.
            x = dx0 - inset
            y0, y1 = dy0, dy1
            v1 = _add_vertex(vertices, vindex, x, y1)
            v2 = _add_vertex(vertices, vindex, x, y0)
        elif door.get("_portal_right") == parent_id:
            # Door west of parent: vertical tripwire, front faces east.
            x = dx1 + inset
            y0, y1 = dy0, dy1
            v1 = _add_vertex(vertices, vindex, x, y0)
            v2 = _add_vertex(vertices, vindex, x, y1)
        elif door.get("_portal_bottom") == parent_id:
            # Door north of parent: horizontal tripwire, front faces south.
            y = dy0 - inset
            x0, x1 = dx0, dx1
            v1 = _add_vertex(vertices, vindex, x0, y)
            v2 = _add_vertex(vertices, vindex, x1, y)
        elif door.get("_portal_top") == parent_id:
            # Door south of parent: horizontal tripwire, front faces north.
            y = dy1 + inset
            x0, x1 = dx0, dx1
            v1 = _add_vertex(vertices, vindex, x1, y)
            v2 = _add_vertex(vertices, vindex, x0, y)
        else:
            continue

        sd = len(sidedefs)
        sidedefs.append(
            {
                "sector": parent_sid,
                "texturetop": DEFAULT_OPEN,
                "texturemiddle": DEFAULT_OPEN,
                "texturebottom": DEFAULT_OPEN,
            }
        )
        # Invisible two-sided walk trigger: both sides same sector.
        sd_back = len(sidedefs)
        sidedefs.append(
            {
                "sector": parent_sid,
                "texturetop": DEFAULT_OPEN,
                "texturemiddle": DEFAULT_OPEN,
                "texturebottom": DEFAULT_OPEN,
            }
        )
        linedefs.append(
            {
                "v1": v1,
                "v2": v2,
                "sidefront": sd,
                "sideback": sd_back,
                "twosided": True,
                "blocking": False,
                "special": DOOR_OPEN_SPECIAL,
                "arg0": tag,
                "arg1": 16,
                "playercross": True,
                "repeatspecial": False,
            }
        )
        applied += 1
    return applied


def _apply_lift_linedefs(
    *,
    rooms: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    sectors: list[Sector],
    sidedefs: list[dict[str, Any]],
    linedefs: list[dict[str, Any]],
) -> int:
    """Walk-on lift: Plat_DownWaitUpStayLip(lip=0) on every portal into the pad."""
    applied = 0
    for room in rooms:
        if not room.get("_lift"):
            continue
        lift_sid = id_to_sector[room["id"]]
        tag = int(room["_lift_tag"])
        sectors[lift_sid].tag = tag
        sectors[lift_sid].wall_texture = SUPPORT_TEX

        for ld in linedefs:
            if not ld.get("twosided") or "sideback" not in ld:
                continue
            sf = sidedefs[ld["sidefront"]]["sector"]
            sb = sidedefs[ld["sideback"]]["sector"]
            if lift_sid not in (sf, sb) or sf == sb:
                continue
            if "special" in ld:
                continue
            # Walk onto / off the pad from either bordering room.
            ld["special"] = PLAT_DOWN_WAIT_UP_STAY_LIP
            ld["arg0"] = tag
            ld["arg1"] = 32
            ld["arg2"] = 105
            ld["arg3"] = 0  # lip 0 — flush with lowest neighbor
            ld["playercross"] = True
            ld["repeatspecial"] = True
            for sdi in (ld["sidefront"], ld["sideback"]):
                sidedefs[sdi]["texturemiddle"] = DEFAULT_OPEN
                if sidedefs[sdi].get("texturebottom") in {DEFAULT_OPEN, DEFAULT_WALL, ""}:
                    sidedefs[sdi]["texturebottom"] = STEP_TEX
            applied += 1
    return applied


@dataclass
class Vertex:
    x: int
    y: int


@dataclass
class Sector:
    floor_height: int
    ceiling_height: int
    floor_flat: str
    ceil_flat: str
    light: int
    wall_texture: str = DEFAULT_WALL
    tag: int | None = None
    special: int | None = None


def _room_bounds(room: dict[str, Any]) -> tuple[int, int, int, int]:
    """Axis-aligned bounds. L-shaped rooms include the wing in the AABB."""
    x, y, w, h = int(room["x"]), int(room["y"]), int(room["w"]), int(room["h"])
    x0, y0, x1, y1 = x, y, x + w, y + h
    if room.get("shape") == "L":
        side = room.get("wing_side", "east")
        ww = int(room.get("wing_w", max(96, w // 2)))
        wh = int(room.get("wing_h", max(96, h // 2)))
        if side == "east":
            x1 = x + w + ww
            y1 = max(y1, y + wh)
        elif side == "west":
            x0 = x - ww
            y1 = max(y1, y + wh)
        elif side == "north":
            y1 = y + h + wh
            x1 = max(x1, x + ww)
        else:
            y0 = y - wh
            x1 = max(x1, x + ww)
    return x0, y0, x1, y1


def _overlap_1d(a0: int, a1: int, b0: int, b1: int) -> tuple[int, int] | None:
    lo = max(a0, b0)
    hi = min(a1, b1)
    if hi <= lo:
        return None
    return lo, hi


def _l_outline_edges(room: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    """Clockwise directed edges (x1,y1,x2,y2) for a true 6-vertex L polygon."""
    x, y, w, h = int(room["x"]), int(room["y"]), int(room["w"]), int(room["h"])
    side = room.get("wing_side", "east")
    ww = int(room.get("wing_w", max(96, w // 2)))
    wh = int(room.get("wing_h", max(96, h // 2)))
    if side == "east":
        # Main [x,y]-[x+w,y+h], wing [x+w,y]-[x+w+ww,y+wh]
        return [
            (x + w + ww, y, x, y),
            (x, y, x, y + h),
            (x, y + h, x + w, y + h),
            (x + w, y + h, x + w, y + wh),
            (x + w, y + wh, x + w + ww, y + wh),
            (x + w + ww, y + wh, x + w + ww, y),
        ]
    if side == "west":
        return [
            (x + w, y, x - ww, y),
            (x - ww, y, x - ww, y + wh),
            (x - ww, y + wh, x, y + wh),
            (x, y + wh, x, y + h),
            (x, y + h, x + w, y + h),
            (x + w, y + h, x + w, y),
        ]
    if side == "north":
        return [
            (x + w, y, x, y),
            (x, y, x, y + h + wh),
            (x, y + h + wh, x + ww, y + h + wh),
            (x + ww, y + h + wh, x + ww, y + h),
            (x + ww, y + h, x + w, y + h),
            (x + w, y + h, x + w, y),
        ]
    # south wing under west portion of main
    return [
        (x + ww, y - wh, x, y - wh),
        (x, y - wh, x, y + h),
        (x, y + h, x + w, y + h),
        (x + w, y + h, x + w, y),
        (x + w, y, x + ww, y),
        (x + ww, y, x + ww, y - wh),
    ]


def _rect_outline_edges(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int, int, int]]:
    return [
        (x1, y0, x0, y0),  # bottom
        (x0, y0, x0, y1),  # left
        (x0, y1, x1, y1),  # top
        (x1, y1, x1, y0),  # right
    ]


def _edge_side(x1: int, y1: int, x2: int, y2: int) -> tuple[str, int, int, int] | None:
    """Return (side, lo, hi, const) for an axis-aligned directed edge, or None."""
    if y1 == y2 and x1 > x2:
        return "bottom", x2, x1, y1
    if y1 == y2 and x2 > x1:
        return "top", x1, x2, y1
    if x1 == x2 and y2 > y1:
        return "left", y1, y2, x1
    if x1 == x2 and y1 > y2:
        return "right", y2, y1, x1
    return None


def _room_outline_edges(room: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    """Directed clockwise outline edges for rect or L rooms."""
    if room.get("shape") == "L":
        return _l_outline_edges(room)
    x0, y0, x1, y1 = _room_bounds(room)
    return _rect_outline_edges(x0, y0, x1, y1)


def _side_span_at(
    room: dict[str, Any], side: str, const: int
) -> tuple[int, int] | None:
    """Merged [lo, hi) along `side` where outline const == edge coordinate.

    L-rooms expose multiple segments per cardinal direction (inner notch +
    outer wing). Corridor attachment must use the segment that actually sits
    on the shared AABB face (e.g. east-wing right at x=aabb_right), not the
    full AABB side length — otherwise openings pack flush into a wing corner
    and look like a half-door, or corridors overhang into void past the wing.
    """
    spans: list[tuple[int, int]] = []
    for ex1, ey1, ex2, ey2 in _room_outline_edges(room):
        meta = _edge_side(ex1, ey1, ex2, ey2)
        if meta is None:
            continue
        s, lo, hi, c = meta
        if s == side and c == const and hi > lo:
            spans.append((lo, hi))
    if not spans:
        return None
    spans.sort()
    merged_lo, merged_hi = spans[0]
    for lo, hi in spans[1:]:
        if lo <= merged_hi:
            merged_hi = max(merged_hi, hi)
        else:
            # Disjoint segments on same face — keep the longest for joining.
            if hi - lo > merged_hi - merged_lo:
                merged_lo, merged_hi = lo, hi
    return merged_lo, merged_hi


def _place_opening(
    overlap: tuple[int, int], width: int
) -> tuple[int, int] | None:
    """Center `width` inside overlap; fall back to max available (>=32)."""
    lo, hi = overlap
    avail = hi - lo
    if avail < 32:
        return None
    w = min(width, avail)
    mid = (lo + hi) // 2
    a = max(lo, mid - w // 2)
    b = min(hi, a + w)
    if b - a < w and a > lo:
        a = max(lo, b - w)
    if b - a < 32:
        a, b = lo, min(hi, lo + width)
    if b - a < 32:
        return None
    return a, b


def materialize_shapes(layout: dict[str, Any]) -> dict[str, Any]:
    """L rooms stay one sector; outline comes from _l_outline_edges. No wing split."""
    return copy.deepcopy(layout)


def _door_fields(
    conn: dict[str, Any],
    index: int,
    floor_a: int,
    floor_b: int,
    open_ceil: int,
) -> dict[str, Any]:
    """Mark synthetic corridor as door, lift, or open passage."""
    lock = conn.get("lock")
    kind = conn.get("kind", "open")
    lo, hi = min(floor_a, floor_b), max(floor_a, floor_b)

    if kind == "lift":
        tag = 1500 + index
        return {
            "floor_height": hi,  # starts flush with upper room
            "ceiling_height": open_ceil,
            "ceil_flat": "FLAT5_4",
            "wall_texture": SUPPORT_TEX,
            "_lift": True,
            "_lift_tag": tag,
            "_lift_low": lo,
        }

    is_door = kind == "door" or lock in LOCK_NUMBERS
    if not is_door:
        return {
            "floor_height": lo,
            "ceiling_height": open_ceil,
        }
    tag = 1000 + index
    # Door pad sits at the lower floor. The higher room gets a step-up through the
    # open door; _apply_door_linedefs must keep STEP lower textures on that face
    # (do not blank texturebottom unconditionally).
    fields: dict[str, Any] = {
        "floor_height": lo,
        "ceiling_height": lo,  # closed door
        "ceil_flat": "FLAT5_4",
        "wall_texture": DOOR_TRACK_TEX,
        "_door": True,
        "_door_tag": tag,
        "_door_open_ceil": open_ceil,
    }
    if lock in LOCK_NUMBERS:
        fields["_lock"] = lock
    return fields


def _make_corridor(
    *,
    cid: str,
    x: int,
    y: int,
    w: int,
    h: int,
    floor_a: int,
    floor_b: int,
    open_ceil: int,
    floor_flat: str,
    ceil_flat: str,
    light: int,
    conn: dict[str, Any],
    index: int,
    portals: dict[str, str],
    wall_texture: str = DEFAULT_WALL,
) -> dict[str, Any]:
    link = _door_fields(conn, index, floor_a, floor_b, open_ceil)
    room = {
        "id": cid,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "floor_flat": floor_flat,
        "ceil_flat": ceil_flat,
        "light": light,
        "wall_texture": wall_texture,
        "_synthetic": True,
        **portals,
        **link,
    }
    return room


def materialize_corridors(layout: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of layout with synthetic corridor rooms for each connection."""
    out = copy.deepcopy(layout)
    rooms = {r["id"]: r for r in out["rooms"]}
    extras: list[dict[str, Any]] = []

    for i, c in enumerate(out.get("connections", [])):
        a, b = rooms.get(c["a"]), rooms.get(c["b"])
        if not a or not b:
            continue
        width = int(c.get("width", 64))
        ax0, ay0, ax1, ay1 = _room_bounds(a)
        bx0, by0, bx1, by1 = _room_bounds(b)

        cid = f"corr_{c['a']}_{c['b']}_{i}"
        light = (int(a.get("light", 160)) + int(b.get("light", 160))) // 2
        floor_a = int(a.get("floor_height", 0))
        floor_b = int(b.get("floor_height", 0))
        ceil_h = min(int(a.get("ceiling_height", 128)), int(b.get("ceiling_height", 128)))
        wall = a.get("wall_texture") or b.get("wall_texture") or DEFAULT_WALL

        def _add(x: int, y: int, w: int, h: int, floor_flat: str, ceil_flat: str, portals: dict[str, str]) -> None:
            extras.append(
                _make_corridor(
                    cid=cid,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    floor_a=floor_a,
                    floor_b=floor_b,
                    open_ceil=ceil_h,
                    floor_flat=floor_flat,
                    ceil_flat=ceil_flat,
                    light=light,
                    conn=c,
                    index=i,
                    portals=portals,
                    wall_texture=wall if c.get("kind") not in {"door", "lift"} and c.get("lock") not in LOCK_NUMBERS else wall,
                )
            )

        # A left of B with a gap
        if ax1 <= bx0:
            gap = bx0 - ax1
            if gap <= 0:
                continue
            # Join on real outline faces (L-wing), not full AABB height.
            a_span = _side_span_at(a, "right", ax1)
            b_span = _side_span_at(b, "left", bx0)
            if not a_span or not b_span:
                continue
            oy = _overlap_1d(a_span[0], a_span[1], b_span[0], b_span[1])
            if not oy:
                continue
            placed = _place_opening(oy, width)
            if not placed:
                continue
            y0, y1 = placed
            _add(
                ax1,
                y0,
                gap,
                y1 - y0,
                a.get("floor_flat", "FLOOR0_1"),
                a.get("ceil_flat", "CEIL1_1"),
                {"_portal_left": c["a"], "_portal_right": c["b"]},
            )
            continue

        # B left of A
        if bx1 <= ax0:
            gap = ax0 - bx1
            if gap <= 0:
                continue
            a_span = _side_span_at(a, "left", ax0)
            b_span = _side_span_at(b, "right", bx1)
            if not a_span or not b_span:
                continue
            oy = _overlap_1d(a_span[0], a_span[1], b_span[0], b_span[1])
            if not oy:
                continue
            placed = _place_opening(oy, width)
            if not placed:
                continue
            y0, y1 = placed
            _add(
                bx1,
                y0,
                gap,
                y1 - y0,
                b.get("floor_flat", "FLOOR0_1"),
                b.get("ceil_flat", "CEIL1_1"),
                {"_portal_left": c["b"], "_portal_right": c["a"]},
            )
            continue

        # A below B with a gap (vertical corridor)
        if ay1 <= by0:
            gap = by0 - ay1
            if gap <= 0:
                continue
            a_span = _side_span_at(a, "top", ay1)
            b_span = _side_span_at(b, "bottom", by0)
            if not a_span or not b_span:
                continue
            ox = _overlap_1d(a_span[0], a_span[1], b_span[0], b_span[1])
            if not ox:
                continue
            placed = _place_opening(ox, width)
            if not placed:
                continue
            x0, x1 = placed
            _add(
                x0,
                ay1,
                x1 - x0,
                gap,
                a.get("floor_flat", "FLOOR0_1"),
                a.get("ceil_flat", "CEIL1_1"),
                {"_portal_bottom": c["a"], "_portal_top": c["b"]},
            )
            continue

        # B below A
        if by1 <= ay0:
            gap = ay0 - by1
            if gap <= 0:
                continue
            a_span = _side_span_at(a, "bottom", ay0)
            b_span = _side_span_at(b, "top", by1)
            if not a_span or not b_span:
                continue
            ox = _overlap_1d(a_span[0], a_span[1], b_span[0], b_span[1])
            if not ox:
                continue
            placed = _place_opening(ox, width)
            if not placed:
                continue
            x0, x1 = placed
            _add(
                x0,
                by1,
                x1 - x0,
                gap,
                b.get("floor_flat", "FLOOR0_1"),
                b.get("ceil_flat", "CEIL1_1"),
                {"_portal_bottom": c["b"], "_portal_top": c["a"]},
            )

    out["rooms"] = list(out["rooms"]) + extras
    return out


def materialize_closets(layout: dict[str, Any]) -> dict[str, Any]:
    """Attach monster closets as rooms + closed door corridors + walk triggers."""
    out = copy.deepcopy(layout)
    rooms = {r["id"]: r for r in out["rooms"]}
    extras: list[dict[str, Any]] = []
    new_conns: list[dict[str, Any]] = []
    new_things: list[dict[str, Any]] = list(out.get("things", []))
    base_tag = 2000

    for i, closet in enumerate(out.get("closets", [])):
        parent = rooms.get(closet["attach_room"])
        if not parent:
            continue
        side = closet.get("side", "east")
        cw = int(closet.get("w", 96))
        ch = int(closet.get("h", 96))
        gap = int(closet.get("gap", 32))
        px0, py0, px1, py1 = _room_bounds(parent)
        cid = closet["id"]
        floor_h = int(closet.get("floor_height", parent.get("floor_height", 0)))
        ceil_h = int(closet.get("ceiling_height", parent.get("ceiling_height", 128)))
        light = int(closet.get("light", 110))

        if side == "east":
            door = {
                "id": f"corr_closet_{cid}",
                "x": px1,
                "y": (py0 + py1 - min(ch, 64)) // 2,
                "w": gap,
                "h": min(ch, 64),
            }
            room = {
                "id": cid,
                "x": px1 + gap,
                "y": door["y"] + (door["h"] - ch) // 2,
                "w": cw,
                "h": ch,
            }
            portals = {"_portal_left": closet["attach_room"], "_portal_right": cid}
        elif side == "west":
            door = {
                "id": f"corr_closet_{cid}",
                "x": px0 - gap,
                "y": (py0 + py1 - min(ch, 64)) // 2,
                "w": gap,
                "h": min(ch, 64),
            }
            room = {
                "id": cid,
                "x": px0 - gap - cw,
                "y": door["y"] + (door["h"] - ch) // 2,
                "w": cw,
                "h": ch,
            }
            portals = {"_portal_left": cid, "_portal_right": closet["attach_room"]}
        elif side == "north":
            door = {
                "id": f"corr_closet_{cid}",
                "x": (px0 + px1 - min(cw, 64)) // 2,
                "y": py1,
                "w": min(cw, 64),
                "h": gap,
            }
            room = {
                "id": cid,
                "x": door["x"] + (door["w"] - cw) // 2,
                "y": py1 + gap,
                "w": cw,
                "h": ch,
            }
            portals = {"_portal_bottom": closet["attach_room"], "_portal_top": cid}
        else:  # south
            door = {
                "id": f"corr_closet_{cid}",
                "x": (px0 + px1 - min(cw, 64)) // 2,
                "y": py0 - gap,
                "w": min(cw, 64),
                "h": gap,
            }
            room = {
                "id": cid,
                "x": door["x"] + (door["w"] - cw) // 2,
                "y": py0 - gap - ch,
                "w": cw,
                "h": ch,
            }
            portals = {"_portal_bottom": cid, "_portal_top": closet["attach_room"]}

        tag = base_tag + i
        door_room = {
            **door,
            "floor_height": floor_h,
            "ceiling_height": floor_h,  # closed
            "floor_flat": parent.get("floor_flat", "FLOOR0_1"),
            "ceil_flat": "FLAT5_4",
            "light": light,
            "wall_texture": DOOR_TRACK_TEX,
            "_synthetic": True,
            "_door": True,
            "_door_tag": tag,
            "_closet_release": True,
            "_closet_trigger": closet.get("trigger", "walk"),
            "_closet_parent": closet["attach_room"],
            **portals,
        }
        closet_room = {
            **room,
            "floor_height": floor_h,
            "ceiling_height": ceil_h,
            "floor_flat": parent.get("floor_flat", "FLOOR0_1"),
            "ceil_flat": parent.get("ceil_flat", "CEIL1_1"),
            "light": light,
            "role": "closet",
            "shape": "alcove",
            "design": closet.get("design", "monster closet"),
            "_closet": True,
        }
        extras.extend([door_room, closet_room])
        rooms[cid] = closet_room
        new_conns.append(
            {
                "a": closet["attach_room"],
                "b": cid,
                "kind": "door",
                "width": min(door["w"], door["h"]),
                "design": closet.get("design", "triggered monster closet"),
            }
        )
        for mon in closet.get("monsters", []):
            new_things.append(
                {
                    "type": mon["type"],
                    "x": closet_room["x"] + int(mon.get("dx", cw // 2)),
                    "y": closet_room["y"] + int(mon.get("dy", ch // 2)),
                    "angle": int(mon.get("angle", 0)),
                }
            )

    out["rooms"] = list(out["rooms"]) + extras
    out["connections"] = list(out.get("connections", [])) + new_conns
    out["things"] = new_things
    return out


def _openings_for_room(
    room: dict[str, Any], corridors: list[dict[str, Any]]
) -> dict[str, list[tuple[int, int]]]:
    """Map side -> list of [lo, hi) opening intervals along that side.

    Intervals are clipped to the real outline span on the AABB face so a
    corridor that overhangs an L-wing cannot punch past the wing into void.
    """
    rid = room["id"]
    x0, y0, x1, y1 = _room_bounds(room)
    openings: dict[str, list[tuple[int, int]]] = {
        "left": [],
        "right": [],
        "bottom": [],
        "top": [],
    }

    def _clip(side: str, const: int, a: int, b: int) -> None:
        span = _side_span_at(room, side, const)
        if not span:
            return
        lo, hi = max(a, span[0]), min(b, span[1])
        if hi > lo:
            openings[side].append((lo, hi))

    for corr in corridors:
        cx0, cy0, cx1, cy1 = _room_bounds(corr)
        if corr.get("_portal_left") == rid and cx0 == x1:
            _clip("right", x1, cy0, cy1)
        if corr.get("_portal_right") == rid and cx1 == x0:
            _clip("left", x0, cy0, cy1)
        if corr.get("_portal_bottom") == rid and cy0 == y1:
            _clip("top", y1, cx0, cx1)
        if corr.get("_portal_top") == rid and cy1 == y0:
            _clip("bottom", y0, cx0, cx1)
    for side in openings:
        openings[side] = sorted(openings[side])
    return openings


def _split_intervals(lo: int, hi: int, holes: list[tuple[int, int]]) -> list[tuple[int, int, bool]]:
    """Return segments (a,b,is_opening) covering [lo,hi)."""
    pts = [lo, hi]
    for a, b in holes:
        pts.extend([max(lo, a), min(hi, b)])
    pts = sorted(set(pts))
    segs: list[tuple[int, int, bool]] = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if a >= b:
            continue
        is_open = any(h0 <= a and b <= h1 for h0, h1 in holes)
        segs.append((a, b, is_open))
    return segs


def _add_vertex(vertices: list[Vertex], index: dict[tuple[int, int], int], x: int, y: int) -> int:
    key = (x, y)
    if key in index:
        return index[key]
    idx = len(vertices)
    vertices.append(Vertex(x, y))
    index[key] = idx
    return idx


def _sidedef_textures(
    *,
    one_sided: bool,
    wall: str,
    front: Sector,
    back: Sector | None,
) -> dict[str, str]:
    """Doom sidedef textures.

    One-sided linedefs need a real middle texture or they render as air/HOM.

    Two-sided openings use '-' middle. Upper/lower fill height gaps as seen
    from THIS sector:
      - upper: this ceiling is above the other (looking into a lower ceiling)
      - lower: this floor is below the other (looking at a raised step)
    Floor risers use classic STEP textures, not the wall texture.
    """
    if one_sided or back is None:
        return {
            "texturetop": DEFAULT_OPEN,
            "texturemiddle": wall,
            "texturebottom": DEFAULT_OPEN,
        }
    upper = wall if front.ceiling_height > back.ceiling_height else DEFAULT_OPEN
    if front.floor_height < back.floor_height:
        # Prefer short step textures for small rises; STEPTOP for taller ledges.
        delta = back.floor_height - front.floor_height
        lower = STEPTOP_TEX if delta >= 48 else STEP_TEX
    else:
        lower = DEFAULT_OPEN
    return {
        "texturetop": upper,
        "texturemiddle": DEFAULT_OPEN,
        "texturebottom": lower,
    }


def _emit_edge(
    *,
    vertices: list[Vertex],
    vindex: dict[tuple[int, int], int],
    sidedefs: list[dict[str, Any]],
    linedefs: list[dict[str, Any]],
    sectors: list[Sector],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    front_sector: int,
    back_sector: int | None,
    wall: str = DEFAULT_WALL,
) -> None:
    """Emit a linedef. Front must face into front_sector (Doom: right side of v1->v2)."""
    v1 = _add_vertex(vertices, vindex, x1, y1)
    v2 = _add_vertex(vertices, vindex, x2, y2)
    front = sectors[front_sector]
    back = sectors[back_sector] if back_sector is not None else None
    one_sided = back_sector is None

    sd_front = len(sidedefs)
    sidedefs.append(
        {
            "sector": front_sector,
            **_sidedef_textures(one_sided=one_sided, wall=wall, front=front, back=back),
        }
    )
    ld: dict[str, Any] = {
        "v1": v1,
        "v2": v2,
        "sidefront": sd_front,
        "blocking": one_sided,
    }
    if back_sector is not None:
        assert back is not None
        sd_back = len(sidedefs)
        # Back sidedef faces into back_sector; swap roles for upper/lower.
        sidedefs.append(
            {
                "sector": back_sector,
                **_sidedef_textures(
                    one_sided=False, wall=wall, front=back, back=front
                ),
            }
        )
        ld["sideback"] = sd_back
        ld["twosided"] = True
        ld["blocking"] = False
    linedefs.append(ld)


def _find_back_sector(
    corridors: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    room_id: str,
    side: str,
    a: int,
    b: int,
    edge_coord: int,
) -> int | None:
    for corr in corridors:
        cx0, cy0, cx1, cy1 = _room_bounds(corr)
        if side == "right" and corr.get("_portal_left") == room_id and cx0 == edge_coord:
            if cy0 <= a and b <= cy1:
                return id_to_sector[corr["id"]]
        if side == "left" and corr.get("_portal_right") == room_id and cx1 == edge_coord:
            if cy0 <= a and b <= cy1:
                return id_to_sector[corr["id"]]
        if side == "top" and corr.get("_portal_bottom") == room_id and cy0 == edge_coord:
            if cx0 <= a and b <= cx1:
                return id_to_sector[corr["id"]]
        if side == "bottom" and corr.get("_portal_top") == room_id and cy1 == edge_coord:
            if cx0 <= a and b <= cx1:
                return id_to_sector[corr["id"]]
    return None


def _emit_cover_props(
    *,
    layout: dict[str, Any],
    rooms: list[dict[str, Any]],
    id_to_sector: dict[str, int],
    sectors: list[Sector],
    vertices: list[Vertex],
    vindex: dict[tuple[int, int], int],
    sidedefs: list[dict[str, Any]],
    linedefs: list[dict[str, Any]],
) -> int:
    """Raised floor blocks / pillars inside rooms for peek cover."""
    room_by_id = {r["id"]: r for r in rooms if not r.get("_synthetic")}
    count = 0
    for prop in layout.get("props", []):
        if prop.get("type") not in {"cover_block", "pillar"}:
            continue
        parent_id = prop.get("in_room")
        parent = room_by_id.get(parent_id) if parent_id else None
        if parent is None:
            # infer room containing center
            cx = int(prop["x"]) + int(prop["w"]) // 2
            cy = int(prop["y"]) + int(prop["h"]) // 2
            for rid, r in room_by_id.items():
                if _point_in_room(cx, cy, r):
                    parent_id = rid
                    parent = r
                    break
        if parent is None or parent_id not in id_to_sector:
            continue
        parent_sid = id_to_sector[parent_id]
        parent_sec = sectors[parent_sid]
        x0, y0 = int(prop["x"]), int(prop["y"])
        x1, y1 = x0 + int(prop["w"]), y0 + int(prop["h"])
        px0, py0, px1, py1 = _room_bounds(parent)
        if x0 < px0 or y0 < py0 or x1 > px1 or y1 > py1:
            continue

        if prop["type"] == "pillar":
            raise_h = int(
                prop.get(
                    "floor_raise",
                    min(96, max(48, parent_sec.ceiling_height - parent_sec.floor_height - 24)),
                )
            )
        else:
            raise_h = int(prop.get("floor_raise", 32))
        floor = parent_sec.floor_height + raise_h
        ceil = parent_sec.ceiling_height
        prop_wall = METAL_TEX if prop["type"] == "pillar" else SUPPORT_TEX
        # Pillars and tall cover (>Doom maxstep 24) must not be walk-through
        # raised platforms. Emit as self-referencing blocking solids (not
        # one-sided hollows — those are true void if the player corner-clips).
        # Short cover_blocks (<=24) stay raised steppable platforms.
        #
        # Inset by 1 mu so prop edges are not colinear with room/corridor walls.
        # Colinear one-sided (or raised) edges that share a portal corner
        # coordinate (e.g. cover south at y=200 with corridor south at y=200)
        # make that portal impassable in GZDoom while still drawing the far
        # floor — the start_hall→plant_hub "blue floor threshold" bug.
        if x1 - x0 > 2 and y1 - y0 > 2:
            x0, y0, x1, y1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
        solid = prop["type"] == "pillar" or raise_h > 24
        if solid:
            # Self-referencing solid: two-sided linedefs with BOTH sides = parent
            # sector and blocking=true. Classic Doom pillar trick — impassable,
            # textured midtex, and NO hollow void interior (one-sided solids let
            # corner-clips / noclip drop the player into true OOB black void).
            edges = [
                (x0, y0, x1, y0),  # bottom
                (x1, y0, x1, y1),  # right
                (x1, y1, x0, y1),  # top
                (x0, y1, x0, y0),  # left
            ]
            for ax, ay, bx, by in edges:
                before = len(linedefs)
                _emit_edge(
                    vertices=vertices,
                    vindex=vindex,
                    sidedefs=sidedefs,
                    linedefs=linedefs,
                    sectors=sectors,
                    x1=ax,
                    y1=ay,
                    x2=bx,
                    y2=by,
                    front_sector=parent_sid,
                    back_sector=parent_sid,
                    wall=prop_wall,
                )
                ld = linedefs[before]
                ld["blocking"] = True
                # Force visible midtex on both faces (emit blanks mid on 2-sided).
                for sdi in (ld["sidefront"], ld["sideback"]):
                    sidedefs[sdi]["texturemiddle"] = prop_wall
                    sidedefs[sdi]["texturetop"] = DEFAULT_OPEN
                    sidedefs[sdi]["texturebottom"] = DEFAULT_OPEN
        else:
            prop_sid = len(sectors)
            sectors.append(
                Sector(
                    floor_height=floor,
                    ceiling_height=ceil,
                    floor_flat=parent_sec.floor_flat,
                    ceil_flat=parent_sec.ceil_flat,
                    light=max(80, parent_sec.light - 20),
                    wall_texture=prop_wall,
                )
            )
            # Clockwise edges so front faces into prop sector; back is parent room.
            edges = [
                (x1, y0, x0, y0),  # bottom
                (x0, y0, x0, y1),  # left
                (x0, y1, x1, y1),  # top
                (x1, y1, x1, y0),  # right
            ]
            for ax, ay, bx, by in edges:
                before = len(linedefs)
                _emit_edge(
                    vertices=vertices,
                    vindex=vindex,
                    sidedefs=sidedefs,
                    linedefs=linedefs,
                    sectors=sectors,
                    x1=ax,
                    y1=ay,
                    x2=bx,
                    y2=by,
                    front_sector=prop_sid,
                    back_sector=parent_sid,
                    wall=prop_wall,
                )
                # Raised props: show METAL/SUPPORT on the room-facing lower, not generic STEP.
                ld = linedefs[before]
                if "sideback" in ld:
                    sidedefs[ld["sideback"]]["texturebottom"] = prop_wall
                    sidedefs[ld["sidefront"]]["texturebottom"] = DEFAULT_OPEN
                    # Soft barrier even for steppable rises helps reduce edge snags.
                    ld["blocking"] = False
        count += 1
    return count


def layout_to_udmf(layout: dict[str, Any]) -> str:
    expanded = materialize_shapes(layout)
    expanded = materialize_corridors(expanded)
    expanded = materialize_closets(expanded)
    rooms = expanded["rooms"]
    corridors = [r for r in rooms if r.get("_synthetic")]
    normal = [r for r in rooms if not r.get("_synthetic")]

    vertices: list[Vertex] = []
    vindex: dict[tuple[int, int], int] = {}
    linedefs: list[dict[str, Any]] = []
    sidedefs: list[dict[str, Any]] = []
    sectors: list[Sector] = []
    things: list[dict[str, Any]] = []

    id_to_sector: dict[str, int] = {}
    for room in rooms:
        id_to_sector[room["id"]] = len(sectors)
        tag = None
        if room.get("_door"):
            tag = int(room["_door_tag"])
        elif room.get("_lift"):
            tag = int(room["_lift_tag"])
        sectors.append(
            Sector(
                floor_height=int(room.get("floor_height", 0)),
                ceiling_height=int(room.get("ceiling_height", 128)),
                floor_flat=room.get("floor_flat", "FLOOR0_1"),
                ceil_flat=room.get("ceil_flat", "CEIL1_1"),
                light=int(room.get("light", 160)),
                wall_texture=room.get("wall_texture", DEFAULT_WALL),
                tag=tag,
                special=int(room["light_special"]) if room.get("light_special") is not None else None,
            )
        )

    # Doom front side = RIGHT of directed linedef. Use clockwise room outlines
    # so the front faces into the sector (one-sided midtex visible from inside).
    for room in normal:
        sid = id_to_sector[room["id"]]
        wall = sectors[sid].wall_texture
        x0, y0, x1, y1 = _room_bounds(room)
        openings = _openings_for_room(room, corridors)
        if room.get("shape") == "L":
            edges = _l_outline_edges(room)
        else:
            edges = _rect_outline_edges(x0, y0, x1, y1)

        for ex1, ey1, ex2, ey2 in edges:
            meta = _edge_side(ex1, ey1, ex2, ey2)
            if meta is None:
                continue
            side, elo, ehi, const = meta
            # Only apply corridor openings that sit on this exact outer edge.
            aabb_const = {"bottom": y0, "left": x0, "top": y1, "right": x1}[side]
            holes = openings[side] if const == aabb_const else []
            for a, b, is_open in _split_intervals(elo, ehi, holes):
                back = (
                    _find_back_sector(corridors, id_to_sector, room["id"], side, a, b, const)
                    if is_open
                    else None
                )
                # Reconstruct directed segment matching original edge orientation.
                if side == "bottom":
                    sx1, sy1, sx2, sy2 = b, const, a, const
                elif side == "top":
                    sx1, sy1, sx2, sy2 = a, const, b, const
                elif side == "left":
                    sx1, sy1, sx2, sy2 = const, a, const, b
                else:  # right
                    sx1, sy1, sx2, sy2 = const, b, const, a
                _emit_edge(
                    vertices=vertices,
                    vindex=vindex,
                    sidedefs=sidedefs,
                    linedefs=linedefs,
                    sectors=sectors,
                    x1=sx1,
                    y1=sy1,
                    x2=sx2,
                    y2=sy2,
                    front_sector=sid,
                    back_sector=back,
                    wall=wall,
                )

    # Corridor outer walls only (portals already emitted from room sides).
    for corr in corridors:
        sid = id_to_sector[corr["id"]]
        wall = sectors[sid].wall_texture
        x0, y0, x1, y1 = _room_bounds(corr)
        # horizontal corridor: top + bottom, clockwise relative to corridor
        if corr.get("_portal_left") is not None:
            _emit_edge(
                vertices=vertices,
                vindex=vindex,
                sidedefs=sidedefs,
                linedefs=linedefs,
                sectors=sectors,
                x1=x1,
                y1=y0,
                x2=x0,
                y2=y0,
                front_sector=sid,
                back_sector=None,
                wall=wall,
            )
            _emit_edge(
                vertices=vertices,
                vindex=vindex,
                sidedefs=sidedefs,
                linedefs=linedefs,
                sectors=sectors,
                x1=x0,
                y1=y1,
                x2=x1,
                y2=y1,
                front_sector=sid,
                back_sector=None,
                wall=wall,
            )
        # vertical corridor: left + right
        if corr.get("_portal_bottom") is not None:
            _emit_edge(
                vertices=vertices,
                vindex=vindex,
                sidedefs=sidedefs,
                linedefs=linedefs,
                sectors=sectors,
                x1=x0,
                y1=y0,
                x2=x0,
                y2=y1,
                front_sector=sid,
                back_sector=None,
                wall=wall,
            )
            _emit_edge(
                vertices=vertices,
                vindex=vindex,
                sidedefs=sidedefs,
                linedefs=linedefs,
                sectors=sectors,
                x1=x1,
                y1=y1,
                x2=x1,
                y2=y0,
                front_sector=sid,
                back_sector=None,
                wall=wall,
            )

    n_props = _emit_cover_props(
        layout=layout,
        rooms=rooms,
        id_to_sector=id_to_sector,
        sectors=sectors,
        vertices=vertices,
        vindex=vindex,
        sidedefs=sidedefs,
        linedefs=linedefs,
    )

    for th in expanded.get("things", []):
        tname = th["type"]
        if tname == "ExitSwitch":
            continue
        ed = THING_ED_NUMBERS.get(tname)
        if ed is None:
            continue
        things.append(
            {
                "type": ed,
                "x": int(th["x"]),
                "y": int(th["y"]),
                "angle": int(th.get("angle", 0)),
                "skill1": True,
                "skill2": True,
                "skill3": True,
                "skill4": True,
                "skill5": True,
                "single": True,
                "coop": True,
                "dm": True,
            }
        )

    n_exits = _apply_exit_linedefs(
        layout=layout,
        rooms=rooms,
        id_to_sector=id_to_sector,
        vertices=vertices,
        linedefs=linedefs,
        sidedefs=sidedefs,
    )
    n_doors = _apply_door_linedefs(
        rooms=rooms,
        id_to_sector=id_to_sector,
        sectors=sectors,
        linedefs=linedefs,
        sidedefs=sidedefs,
    )
    n_tripwires = _apply_closet_tripwires(
        rooms=rooms,
        id_to_sector=id_to_sector,
        vertices=vertices,
        vindex=vindex,
        sidedefs=sidedefs,
        linedefs=linedefs,
    )
    n_lifts = _apply_lift_linedefs(
        rooms=rooms,
        id_to_sector=id_to_sector,
        sectors=sectors,
        linedefs=linedefs,
        sidedefs=sidedefs,
    )

    lines: list[str] = [
        'namespace = "zdoom";',
        f"// map: {layout.get('name', 'MAP01')}",
        f"// theme: {layout.get('theme', '')}",
        (
            f"// rooms={len(normal)} corridors={len(corridors)} "
            f"exits={n_exits} doors={n_doors} props={n_props} "
            f"tripwires={n_tripwires} lifts={n_lifts}"
        ),
        "// linedefs clockwise so front midtex faces into sector",
    ]

    for i, v in enumerate(vertices):
        lines += [f"vertex // {i}", "{", f"  x = {v.x}.000;", f"  y = {v.y}.000;", "}"]

    for i, s in enumerate(sectors):
        lines += [
            f"sector // {i}",
            "{",
            f"  heightfloor = {s.floor_height};",
            f"  heightceiling = {s.ceiling_height};",
            f'  texturefloor = "{s.floor_flat}";',
            f'  textureceiling = "{s.ceil_flat}";',
            f"  lightlevel = {s.light};",
        ]
        if s.special is not None:
            lines.append(f"  special = {s.special};")
        if s.tag is not None:
            lines.append(f"  id = {s.tag};")
        lines.append("}")

    for i, sd in enumerate(sidedefs):
        lines += [
            f"sidedef // {i}",
            "{",
            f"  sector = {sd['sector']};",
            f'  texturetop = "{sd["texturetop"]}";',
            f'  texturemiddle = "{sd["texturemiddle"]}";',
            f'  texturebottom = "{sd["texturebottom"]}";',
            "}",
        ]

    for i, ld in enumerate(linedefs):
        lines.append(f"linedef // {i}")
        lines.append("{")
        lines.append(f"  v1 = {ld['v1']};")
        lines.append(f"  v2 = {ld['v2']};")
        lines.append(f"  sidefront = {ld['sidefront']};")
        if "sideback" in ld:
            lines.append(f"  sideback = {ld['sideback']};")
        if ld.get("twosided"):
            lines.append("  twosided = true;")
        if ld.get("blocking"):
            lines.append("  blocking = true;")
        if "special" in ld:
            lines.append(f"  special = {ld['special']};")
            for ai in range(5):
                key = f"arg{ai}"
                if key in ld:
                    lines.append(f"  {key} = {ld[key]};")
        if ld.get("playeruse"):
            lines.append("  playeruse = true;")
        if ld.get("playercross"):
            lines.append("  playercross = true;")
        if ld.get("repeatspecial"):
            lines.append("  repeatspecial = true;")
        lines.append("}")

    for i, th in enumerate(things):
        lines.append(f"thing // {i}")
        lines.append("{")
        for k, val in th.items():
            if isinstance(val, bool):
                lines.append(f"  {k} = {'true' if val else 'false'};")
            else:
                lines.append(f"  {k} = {val};")
        lines.append("}")

    return "\n".join(lines) + "\n"


def write_textmap_wad(udmf_text: str, out_path: Path, map_name: str = "MAP01") -> Path:
    """Write a minimal UDMF PWAD: MAP01 + TEXTMAP + ENDMAP."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    textmap = udmf_text.encode("utf-8")
    lumps: list[tuple[str, bytes]] = [
        (map_name, b""),
        ("TEXTMAP", textmap),
        ("ENDMAP", b""),
    ]

    header_size = 12
    payloads: list[bytes] = []
    directory = bytearray()
    offset = header_size
    for name, data in lumps:
        payloads.append(data)
        directory += struct.pack("<II", offset, len(data))
        directory += name.encode("ascii")[:8].ljust(8, b"\x00")
        offset += len(data)

    header = b"PWAD" + struct.pack("<II", len(lumps), offset)
    with out_path.open("wb") as f:
        f.write(header)
        for p in payloads:
            f.write(p)
        f.write(directory)

    out_path.with_suffix(".txt").write_text(udmf_text, encoding="utf-8")
    return out_path
