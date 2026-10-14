"""Hull integrity + walkability gate for JSON→WAD.

Non-negotiable: refuse to ship a PWAD that fails these checks.
Player radius is Doom's standard 16 map units.
"""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from udmf.writer import (
    _edge_side,
    _openings_for_room,
    _point_in_room,
    _room_bounds,
    _room_outline_edges,
    _side_span_at,
    layout_to_udmf,
    materialize_closets,
    materialize_corridors,
    materialize_shapes,
)

PLAYER_R = 16
WALK_STEP = 16
PORTAL_APPROACH = 64  # how far into rooms the portal "approach axis" extends


@dataclass
class HullIssue:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def parse_udmf(text: str):
    verts, sectors, sidedefs, linedefs = [], [], [], []
    for m in re.finditer(
        r"(vertex|linedef|sidedef|sector)\s*(?://[^\n]*)?\s*\{([^}]*)\}", text
    ):
        kind, body = m.group(1), m.group(2)
        fields: dict = {}
        for fm in re.finditer(r"(\w+)\s*=\s*([^;]+);", body):
            k, v = fm.group(1), fm.group(2).strip()
            if v in ("true", "false"):
                fields[k] = v == "true"
            elif v.startswith('"'):
                fields[k] = v.strip('"')
            else:
                try:
                    fields[k] = int(float(v)) if "." in v else int(v)
                except ValueError:
                    fields[k] = v
        {
            "vertex": verts,
            "sector": sectors,
            "sidedef": sidedefs,
            "linedef": linedefs,
        }[kind].append(fields)
    return verts, sectors, sidedefs, linedefs


def winding_sector(px, py, verts, sidedefs, linedefs, sectors):
    best = None
    best_abs = 0
    best_floor = -1e9
    for sid in range(len(sectors)):
        w = 0
        for ld in linedefs:
            sf = sidedefs[ld["sidefront"]]["sector"]
            sb = sidedefs[ld["sideback"]]["sector"] if "sideback" in ld else None
            if sf == sb == sid:
                continue
            if sf == sid:
                v1, v2 = ld["v1"], ld["v2"]
            elif sb == sid:
                v1, v2 = ld["v2"], ld["v1"]
            else:
                continue
            x1, y1 = verts[v1]["x"], verts[v1]["y"]
            x2, y2 = verts[v2]["x"], verts[v2]["y"]
            if y1 == y2:
                continue
            if y1 <= py < y2 or y2 <= py < y1:
                t = (py - y1) / (y2 - y1)
                xint = x1 + t * (x2 - x1)
                if xint > px:
                    w += 1 if y2 > y1 else -1
        if w != 0:
            fl = sectors[sid].get("heightfloor", 0)
            if best is None or abs(w) > best_abs or (
                abs(w) == best_abs and fl >= best_floor
            ):
                best, best_abs, best_floor = sid, abs(w), fl
    return best


def blocking_segs(linedefs, verts):
    segs = []
    for ld in linedefs:
        if "sideback" not in ld or ld.get("blocking"):
            v1, v2 = verts[ld["v1"]], verts[ld["v2"]]
            segs.append((v1["x"], v1["y"], v2["x"], v2["y"]))
    return segs


def near_block(px, py, segs, r=PLAYER_R) -> bool:
    for x1, y1, x2, y2 in segs:
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 == 0:
            d = math.hypot(px - x1, py - y1)
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / l2))
            d = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
        if d < r - 0.1:
            return True
    return False


def _solid_props(layout: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in layout.get("props", []):
        rh = int(p.get("floor_raise", 96 if p["type"] == "pillar" else 32))
        if p["type"] == "pillar" or rh > 24:
            out.append(p)
    return out


def _prop_inflated(p: dict[str, Any], pad: int = PLAYER_R) -> tuple[int, int, int, int]:
    return (
        int(p["x"]) - pad,
        int(p["y"]) - pad,
        int(p["x"]) + int(p["w"]) + pad,
        int(p["y"]) + int(p["h"]) + pad,
    )


def _in_rect(px: float, py: float, r: tuple[int, int, int, int]) -> bool:
    return r[0] <= px < r[2] and r[1] <= py < r[3]


def _rects_overlap(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _ld_span(ld, verts):
    x1, y1 = verts[ld["v1"]]["x"], verts[ld["v1"]]["y"]
    x2, y2 = verts[ld["v2"]]["x"], verts[ld["v2"]]["y"]
    if y1 == y2:
        return ("h", y1, min(x1, x2), max(x1, x2))
    if x1 == x2:
        return ("v", x1, min(y1, y2), max(y1, y2))
    return None


def _closet_aabb(
    closet: dict[str, Any], parent: dict[str, Any]
) -> tuple[int, int, int, int]:
    side = closet.get("side", "east")
    cw = int(closet.get("w", 96))
    ch = int(closet.get("h", 96))
    gap = int(closet.get("gap", 32))
    px0, py0, px1, py1 = _room_bounds(parent)
    if side == "east":
        x0 = px1 + gap
        y0 = (py0 + py1 - ch) // 2
        return x0, y0, x0 + cw, y0 + ch
    if side == "west":
        x0 = px0 - gap - cw
        y0 = (py0 + py1 - ch) // 2
        return x0, y0, x0 + cw, y0 + ch
    if side == "north":
        x0 = (px0 + px1 - cw) // 2
        y0 = py1 + gap
        return x0, y0, x0 + cw, y0 + ch
    x0 = (px0 + px1 - cw) // 2
    y0 = py0 - gap - ch
    return x0, y0, x0 + cw, y0 + ch


def check_layout_overlaps(layout: dict[str, Any]) -> list[HullIssue]:
    """Room AABB/polygon overlaps + closet vs room overlaps (pre-UDMF)."""
    issues: list[HullIssue] = []
    rooms = list(layout.get("rooms", []))
    for i, a in enumerate(rooms):
        ax0, ay0, ax1, ay1 = _room_bounds(a)
        for b in rooms[i + 1 :]:
            bx0, by0, bx1, by1 = _room_bounds(b)
            ox0, oy0 = max(ax0, bx0), max(ay0, by0)
            ox1, oy1 = min(ax1, bx1), min(ay1, by1)
            if ox0 >= ox1 or oy0 >= oy1:
                continue
            hit = False
            for x in range(ox0 + 4, ox1, 8):
                for y in range(oy0 + 4, oy1, 8):
                    if _point_in_room(x, y, a) and _point_in_room(x, y, b):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                issues.append(
                    HullIssue(
                        "ROOM_OVERLAP",
                        f"{a['id']} vs {b['id']}",
                    )
                )

    rooms_by_id = {r["id"]: r for r in rooms}
    for closet in layout.get("closets", []):
        parent = rooms_by_id.get(closet.get("attach_room"))
        if not parent:
            continue
        cx0, cy0, cx1, cy1 = _closet_aabb(closet, parent)
        for r in rooms:
            if r["id"] == parent["id"]:
                continue
            rx0, ry0, rx1, ry1 = _room_bounds(r)
            if _rects_overlap((cx0, cy0, cx1, cy1), (rx0, ry0, rx1, ry1)):
                issues.append(
                    HullIssue(
                        "CLOSET_ROOM_OVERLAP",
                        f"closet {closet.get('id')} vs room {r['id']}",
                    )
                )
    return issues


def check_prop_vs_portal(
    layout: dict[str, Any], expanded: dict[str, Any]
) -> list[HullIssue]:
    """Solids must not sit on the midline / approach axis of a connection."""
    issues: list[HullIssue] = []
    rooms = {r["id"]: r for r in expanded["rooms"]}
    solids = _solid_props(layout)
    for i, c in enumerate(layout.get("connections", [])):
        cid = f"corr_{c['a']}_{c['b']}_{i}"
        corr = rooms.get(cid)
        if not corr:
            continue
        cx0, cy0, cx1, cy1 = _room_bounds(corr)
        # Corridor footprint itself (player must cross).
        strips = [(cx0, cy0, cx1, cy1)]
        # Extend approach axis into both rooms along corridor direction.
        if corr.get("_portal_left") is not None:  # horizontal corridor
            mid_y0 = cy0
            mid_y1 = cy1
            strips.append((cx0 - PORTAL_APPROACH, mid_y0, cx0, mid_y1))
            strips.append((cx1, mid_y0, cx1 + PORTAL_APPROACH, mid_y1))
            # Midline band (center third of corridor height, full length + approaches)
            my = (cy0 + cy1) // 2
            band = max(PLAYER_R, (cy1 - cy0) // 3)
            strips.append(
                (cx0 - PORTAL_APPROACH, my - band, cx1 + PORTAL_APPROACH, my + band)
            )
        else:  # vertical corridor
            mid_x0 = cx0
            mid_x1 = cx1
            strips.append((mid_x0, cy0 - PORTAL_APPROACH, mid_x1, cy0))
            strips.append((mid_x0, cy1, mid_x1, cy1 + PORTAL_APPROACH))
            mx = (cx0 + cx1) // 2
            band = max(PLAYER_R, (cx1 - cx0) // 3)
            strips.append(
                (mx - band, cy0 - PORTAL_APPROACH, mx + band, cy1 + PORTAL_APPROACH)
            )

        for p in solids:
            prect = (int(p["x"]), int(p["y"]), int(p["x"]) + int(p["w"]), int(p["y"]) + int(p["h"]))
            for s in strips:
                if _rects_overlap(prect, s):
                    issues.append(
                        HullIssue(
                            "PROP_ON_PORTAL_MIDLINE",
                            f"{p['type']}@{p['x']},{p['y']} blocks {cid} "
                            f"({c.get('kind', 'open')})",
                        )
                    )
                    break
    return issues


def check_corridor_clearance(expanded: dict[str, Any]) -> list[HullIssue]:
    """Corridors narrower than 2*player radius cannot be crossed fairly."""
    issues: list[HullIssue] = []
    for r in expanded["rooms"]:
        if not r.get("_synthetic"):
            continue
        x0, y0, x1, y1 = _room_bounds(r)
        w, h = x1 - x0, y1 - y0
        clear = min(w, h)
        if clear < 2 * PLAYER_R:
            issues.append(
                HullIssue(
                    "CORRIDOR_TOO_NARROW",
                    f"{r['id']} clearance={clear} < {2 * PLAYER_R}",
                )
            )
    return issues


def walkability_bfs(
    layout: dict[str, Any],
    expanded: dict[str, Any],
    *,
    segs: list[tuple[int, int, int, int]] | None = None,
) -> list[HullIssue]:
    """Grid BFS from Player1Start to ExitSwitch with player radius clearance."""
    issues: list[HullIssue] = []
    start = next((t for t in layout.get("things", []) if t["type"] == "Player1Start"), None)
    exit_th = next((t for t in layout.get("things", []) if t["type"] == "ExitSwitch"), None)
    if not start:
        issues.append(HullIssue("WALK_NO_START", "missing Player1Start"))
        return issues
    if not exit_th:
        # Prototypes may omit ExitSwitch — require spawn to all normal rooms.
        return _walkability_all_rooms(layout, expanded, start, segs)

    walk_rooms = [
        r
        for r in expanded["rooms"]
        if not r.get("_closet")  # monster via tripwire; don't require grid into closet
    ]
    # Closed door corridors still count as walkable for pathing (player opens them).
    solids = [_prop_inflated(p, PLAYER_R) for p in _solid_props(layout)]

    def cell_ok(px: int, py: int) -> bool:
        if not any(_point_in_room(px, py, r) for r in walk_rooms):
            return False
        if any(_in_rect(px, py, s) for s in solids):
            return False
        if segs is not None and near_block(px, py, segs, PLAYER_R):
            return False
        return True

    sx, sy = int(start["x"]), int(start["y"])
    ex, ey = int(exit_th["x"]), int(exit_th["y"])
    # Snap to step grid
    def snap(v: int) -> int:
        return (v // WALK_STEP) * WALK_STEP + WALK_STEP // 2

    start_c = (snap(sx), snap(sy))
    goal_c = (snap(ex), snap(ey))
    # If snapped cell blocked, try original then neighbors
    def seed(x: int, y: int) -> tuple[int, int] | None:
        for cx, cy in (
            (snap(x), snap(y)),
            (x, y),
            (snap(x) + WALK_STEP, snap(y)),
            (snap(x) - WALK_STEP, snap(y)),
            (snap(x), snap(y) + WALK_STEP),
            (snap(x), snap(y) - WALK_STEP),
        ):
            if cell_ok(cx, cy):
                return (cx, cy)
        return None

    s0 = seed(sx, sy)
    g0 = seed(ex, ey)
    if s0 is None:
        issues.append(HullIssue("WALK_START_BLOCKED", f"spawn ({sx},{sy}) not clear r={PLAYER_R}"))
        return issues
    if g0 is None:
        issues.append(HullIssue("WALK_EXIT_BLOCKED", f"exit ({ex},{ey}) not clear r={PLAYER_R}"))
        return issues

    q = deque([s0])
    seen = {s0}
    found = False
    # Bound search
    min_x = min(_room_bounds(r)[0] for r in walk_rooms) - WALK_STEP
    max_x = max(_room_bounds(r)[2] for r in walk_rooms) + WALK_STEP
    min_y = min(_room_bounds(r)[1] for r in walk_rooms) - WALK_STEP
    max_y = max(_room_bounds(r)[3] for r in walk_rooms) + WALK_STEP
    while q:
        x, y = q.popleft()
        if abs(x - g0[0]) <= WALK_STEP and abs(y - g0[1]) <= WALK_STEP:
            found = True
            break
        for dx, dy in ((WALK_STEP, 0), (-WALK_STEP, 0), (0, WALK_STEP), (0, -WALK_STEP)):
            nx, ny = x + dx, y + dy
            if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                continue
            if (nx, ny) in seen:
                continue
            if not cell_ok(nx, ny):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))

    if not found:
        issues.append(
            HullIssue(
                "WALKABILITY_BFS_FAIL",
                f"no r={PLAYER_R} path spawn→exit "
                f"(visited {len(seen)} cells; start={s0} goal={g0})",
            )
        )
    return issues


def _walkability_all_rooms(
    layout: dict[str, Any],
    expanded: dict[str, Any],
    start: dict[str, Any],
    segs: list[tuple[int, int, int, int]] | None,
) -> list[HullIssue]:
    """Fallback when no ExitSwitch: spawn must reach every normal room center."""
    issues: list[HullIssue] = []
    walk_rooms = [r for r in expanded["rooms"] if not r.get("_closet")]
    normals = [r for r in walk_rooms if not r.get("_synthetic")]
    solids = [_prop_inflated(p, PLAYER_R) for p in _solid_props(layout)]

    def cell_ok(px: int, py: int) -> bool:
        if not any(_point_in_room(px, py, r) for r in walk_rooms):
            return False
        if any(_in_rect(px, py, s) for s in solids):
            return False
        if segs is not None and near_block(px, py, segs, PLAYER_R):
            return False
        return True

    def snap(v: int) -> int:
        return (v // WALK_STEP) * WALK_STEP + WALK_STEP // 2

    def seed(x: int, y: int) -> tuple[int, int] | None:
        for cx, cy in ((snap(x), snap(y)), (x, y)):
            if cell_ok(cx, cy):
                return (cx, cy)
        return None

    sx, sy = int(start["x"]), int(start["y"])
    s0 = seed(sx, sy)
    if s0 is None:
        issues.append(HullIssue("WALK_START_BLOCKED", f"spawn ({sx},{sy}) not clear r={PLAYER_R}"))
        return issues

    q = deque([s0])
    seen = {s0}
    min_x = min(_room_bounds(r)[0] for r in walk_rooms) - WALK_STEP
    max_x = max(_room_bounds(r)[2] for r in walk_rooms) + WALK_STEP
    min_y = min(_room_bounds(r)[1] for r in walk_rooms) - WALK_STEP
    max_y = max(_room_bounds(r)[3] for r in walk_rooms) + WALK_STEP
    while q:
        x, y = q.popleft()
        for dx, dy in ((WALK_STEP, 0), (-WALK_STEP, 0), (0, WALK_STEP), (0, -WALK_STEP)):
            nx, ny = x + dx, y + dy
            if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                continue
            if (nx, ny) in seen or not cell_ok(nx, ny):
                continue
            seen.add((nx, ny))
            q.append((nx, ny))

    for r in normals:
        cx = int(r["x"]) + int(r["w"]) // 2
        cy = int(r["y"]) + int(r["h"]) // 2
        g = seed(cx, cy)
        if g is None:
            issues.append(
                HullIssue(
                    "WALKABILITY_BFS_FAIL",
                    f"room:{r['id']} center not clear r={PLAYER_R}",
                )
            )
            continue
        if g not in seen and not any(
            abs(vx - g[0]) <= WALK_STEP and abs(vy - g[1]) <= WALK_STEP for vx, vy in seen
        ):
            issues.append(
                HullIssue(
                    "WALKABILITY_BFS_FAIL",
                    f"no r={PLAYER_R} path spawn→room:{r['id']} center",
                )
            )
    return issues


def audit_portal_punches(
    layout: dict[str, Any],
    expanded: dict[str, Any],
    verts,
    sidedefs,
    linedefs,
) -> list[HullIssue]:
    issues: list[HullIssue] = []
    rooms = {r["id"]: r for r in expanded["rooms"]}
    corridors = [r for r in expanded["rooms"] if r.get("_synthetic")]
    conns = layout.get("connections", [])

    by_axis: dict[tuple, list] = {}
    for i, ld in enumerate(linedefs):
        span = _ld_span(ld, verts)
        if not span:
            continue
        orient, const, lo, hi = span
        one = "sideback" not in ld
        by_axis.setdefault((orient, const), []).append(
            {
                "i": i,
                "lo": lo,
                "hi": hi,
                "one": one,
                "special": ld.get("special"),
                "blocking": ld.get("blocking", one),
            }
        )

    for key, segs in by_axis.items():
        portals = [s for s in segs if not s["one"]]
        walls = [s for s in segs if s["one"]]
        for p in portals:
            for w in walls:
                olo, ohi = max(p["lo"], w["lo"]), min(p["hi"], w["hi"])
                if ohi > olo:
                    issues.append(
                        HullIssue(
                            "PORTAL_WALL_OVERLAP",
                            f"{key} portal LD{p['i']} [{p['lo']},{p['hi']}] "
                            f"vs wall LD{w['i']} [{w['lo']},{w['hi']}]",
                        )
                    )

    for i, c in enumerate(conns):
        a, b = rooms.get(c["a"]), rooms.get(c["b"])
        if not a or not b:
            continue
        want = int(c.get("width", 64))
        cid = f"corr_{c['a']}_{c['b']}_{i}"
        corr = rooms.get(cid)
        if not corr:
            continue
        cx0, cy0, cx1, cy1 = _room_bounds(corr)
        ax0, ay0, ax1, ay1 = _room_bounds(a)
        parent = None
        side = ""
        orient = const = glo = ghi = None
        if corr.get("_portal_left") == a["id"] and cx0 == ax1:
            orient, const, glo, ghi = "v", ax1, cy0, cy1
            parent, side = a, "right"
        elif corr.get("_portal_right") == a["id"] and cx1 == ax0:
            orient, const, glo, ghi = "v", ax0, cy0, cy1
            parent, side = a, "left"
        elif corr.get("_portal_bottom") == a["id"] and cy0 == ay1:
            orient, const, glo, ghi = "h", ay1, cx0, cx1
            parent, side = a, "top"
        elif corr.get("_portal_top") == a["id"] and cy1 == ay0:
            orient, const, glo, ghi = "h", ay0, cx0, cx1
            parent, side = a, "bottom"
        else:
            bx0, by0, bx1, by1 = _room_bounds(b)
            if corr.get("_portal_left") == b["id"] and cx0 == bx1:
                orient, const, glo, ghi = "v", bx1, cy0, cy1
                parent, side = b, "right"
            elif corr.get("_portal_right") == b["id"] and cx1 == bx0:
                orient, const, glo, ghi = "v", bx0, cy0, cy1
                parent, side = b, "left"
            elif corr.get("_portal_bottom") == b["id"] and cy0 == by1:
                orient, const, glo, ghi = "h", by1, cx0, cx1
                parent, side = b, "top"
            elif corr.get("_portal_top") == b["id"] and cy1 == by0:
                orient, const, glo, ghi = "h", by0, cx0, cx1
                parent, side = b, "bottom"
            else:
                issues.append(HullIssue("PORTAL_UNATTACHED", cid))
                continue

        assert parent is not None and glo is not None and ghi is not None
        gap = ghi - glo
        span = _side_span_at(parent, side, const)
        if not span or glo < span[0] - 0.1 or ghi > span[1] + 0.1:
            issues.append(
                HullIssue(
                    "PORTAL_PAST_EDGE",
                    f"{cid} {side}@{const} corr[{glo},{ghi}] edge={span}",
                )
            )

        covered = 0
        segs = by_axis.get((orient, const), [])
        for s in segs:
            if s["one"]:
                continue
            olo, ohi = max(glo, s["lo"]), min(ghi, s["hi"])
            if ohi > olo:
                covered += ohi - olo
        if covered < gap - 1:
            issues.append(
                HullIssue(
                    "PORTAL_INCOMPLETE_PUNCH",
                    f"{cid} want_gap={gap} twosided_cover={covered} width={want}",
                )
            )
        if corr.get("_door") or corr.get("_lift"):
            for s in segs:
                if not s["one"]:
                    continue
                olo, ohi = max(glo, s["lo"]), min(ghi, s["hi"])
                if ohi > olo:
                    issues.append(
                        HullIssue(
                            "DOOR_SIBLING_WALL",
                            f"{cid} LD{s['i']} blocks [{olo},{ohi}] of portal "
                            f"[{glo},{ghi}] ({'lift' if corr.get('_lift') else 'door'})",
                        )
                    )

    for room in expanded["rooms"]:
        if room.get("_synthetic") or room.get("shape") != "L":
            continue
        opens = _openings_for_room(room, corridors)
        for ex1, ey1, ex2, ey2 in _room_outline_edges(room):
            meta = _edge_side(ex1, ey1, ex2, ey2)
            if not meta:
                continue
            side, elo, ehi, const = meta
            edge_len = ehi - elo
            if edge_len < 96:
                continue
            for h0, h1 in opens.get(side, []):
                if h0 < elo or h1 > ehi:
                    continue
                flush = h0 == elo or h1 == ehi
                frac = (h1 - h0) / edge_len
                if flush and 0.3 <= frac <= 0.7:
                    span = _side_span_at(room, side, const)
                    if span and span[0] == elo and span[1] == ehi:
                        issues.append(
                            HullIssue(
                                "HALF_PORTAL_APPEARANCE",
                                f"{room['id']} {side}@{const} "
                                f"edge[{elo},{ehi}] open[{h0},{h1}] flush",
                            )
                        )
    return issues


def audit_layout(layout: dict[str, Any], *, udmf_text: str | None = None) -> list[HullIssue]:
    """Full hull + walkability audit. Empty list = shippable."""
    issues: list[HullIssue] = []
    issues.extend(check_layout_overlaps(layout))

    expanded = materialize_closets(materialize_corridors(materialize_shapes(layout)))
    issues.extend(check_prop_vs_portal(layout, expanded))
    issues.extend(check_corridor_clearance(expanded))

    # Expanded room overlaps (includes closets as rooms)
    normals = [r for r in expanded["rooms"] if not r.get("_synthetic")]
    for i, a in enumerate(normals):
        ax0, ay0, ax1, ay1 = _room_bounds(a)
        for b in normals[i + 1 :]:
            bx0, by0, bx1, by1 = _room_bounds(b)
            ox0, oy0 = max(ax0, bx0), max(ay0, by0)
            ox1, oy1 = min(ax1, bx1), min(ay1, by1)
            if ox0 >= ox1 or oy0 >= oy1:
                continue
            hit = False
            for x in range(ox0 + 4, ox1, 8):
                for y in range(oy0 + 4, oy1, 8):
                    if _point_in_room(x, y, a) and _point_in_room(x, y, b):
                        hit = True
                        break
                if hit:
                    break
            if hit and not any(
                iss.code == "ROOM_OVERLAP"
                and a["id"] in iss.message
                and b["id"] in iss.message
                for iss in issues
            ):
                issues.append(HullIssue("ROOM_OVERLAP", f"{a['id']} vs {b['id']} (expanded)"))

    text = udmf_text if udmf_text is not None else layout_to_udmf(layout)
    verts, sectors, sidedefs, linedefs = parse_udmf(text)
    id_map = {r["id"]: i for i, r in enumerate(expanded["rooms"])}
    segs = blocking_segs(linedefs, verts)

    for p in _solid_props(layout):
        cx = p["x"] + p["w"] // 2
        cy = p["y"] + p["h"] // 2
        sid = winding_sector(cx + 0.5, cy + 0.5, verts, sidedefs, linedefs, sectors)
        parent = id_map.get(p.get("in_room"))
        if sid != parent:
            issues.append(
                HullIssue(
                    "PROP_VOID",
                    f"{p['type']}@{p['x']},{p['y']} sid={sid} want={parent}",
                )
            )

    # Probe spawn, rooms, corridors
    probes: list[tuple[str, int, int]] = []
    for th in layout.get("things", []):
        if th["type"] == "Player1Start":
            probes.append(("spawn", int(th["x"]), int(th["y"])))
    for r in expanded["rooms"]:
        x0, y0, x1, y1 = _room_bounds(r)
        if r.get("_synthetic") and not r.get("_closet_release"):
            probes.append((f"corr:{r['id']}", (x0 + x1) // 2, (y0 + y1) // 2))
        elif not r.get("_synthetic") and not r.get("_closet"):
            cx = int(r["x"]) + int(r["w"]) // 2
            cy = int(r["y"]) + int(r["h"]) // 2
            for p in _solid_props(layout):
                if (
                    p.get("in_room") == r["id"]
                    and p["x"] - 8 <= cx <= p["x"] + p["w"] + 8
                    and p["y"] - 8 <= cy <= p["y"] + p["h"] + 8
                ):
                    cx, cy = int(r["x"]) + 24, int(r["y"]) + 24
                    break
            probes.append((f"room:{r['id']}", cx, cy))

    for label, x, y in probes:
        sid = winding_sector(x + 0.5, y + 0.5, verts, sidedefs, linedefs, sectors)
        if sid is None:
            issues.append(HullIssue("VOID", f"{label} ({x},{y})"))
        elif label.startswith("corr:") and near_block(x, y, segs, PLAYER_R):
            issues.append(HullIssue("BLOCKED", f"{label} ({x},{y})"))

    for i, ld in enumerate(linedefs):
        if not (ld.get("twosided") and ld.get("blocking")):
            continue
        sf = sidedefs[ld["sidefront"]]["sector"]
        sb = sidedefs[ld["sideback"]]["sector"]
        if sf != sb:
            issues.append(
                HullIssue("PORTAL_BLOCKING", f"LD{i} sectors {sf}/{sb}")
            )

    issues.extend(audit_portal_punches(layout, expanded, verts, sidedefs, linedefs))
    issues.extend(walkability_bfs(layout, expanded, segs=segs))
    return issues


def audit_report(layout: dict[str, Any], *, udmf_text: str | None = None) -> dict[str, Any]:
    issues = audit_layout(layout, udmf_text=udmf_text)
    return {
        "ok": len(issues) == 0,
        "n_issues": len(issues),
        "player_radius": PLAYER_R,
        "issues": [asdict(i) for i in issues],
    }


def assert_hull_ok(layout: dict[str, Any], *, udmf_text: str | None = None) -> dict[str, Any]:
    """Raise ValueError if hull/walkability fails. Returns report if OK."""
    report = audit_report(layout, udmf_text=udmf_text)
    if report["ok"]:
        return report
    lines = [f"{i['code']}: {i['message']}" for i in report["issues"]]
    raise ValueError(
        "hull/walkability gate failed — refusing to emit WAD:\n- " + "\n- ".join(lines)
    )
