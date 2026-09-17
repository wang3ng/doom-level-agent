#!/usr/bin/env python3
"""Geometry hull audit + critical-path walkability for generated UDMF maps.

Reports: room overlaps, solid-prop interior sector (must not be void),
corridor clearance (player r=16), portal blocking flags, critical-path probes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from udmf.writer import (  # noqa: E402
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
                continue  # self-ref internal barrier
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


def near_block(px, py, segs, r=16):
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


def audit(name: str) -> int:
    layout = json.loads((ROOT / f"data/layouts/{name}.json").read_text())
    text = layout_to_udmf(layout)
    verts, sectors, sidedefs, linedefs = parse_udmf(text)
    expanded = materialize_closets(materialize_corridors(materialize_shapes(layout)))
    id_map = {r["id"]: i for i, r in enumerate(expanded["rooms"])}
    segs = blocking_segs(linedefs, verts)

    print(f"=== {name} ===")
    fails = 0

    # overlaps
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
            if hit:
                print(f"  OVERLAP {a['id']} vs {b['id']}")
                fails += 1

    # solid prop interiors
    for p in layout.get("props", []):
        rh = p.get("floor_raise", 96 if p["type"] == "pillar" else 32)
        solid = p["type"] == "pillar" or rh > 24
        if not solid:
            continue
        cx = p["x"] + p["w"] // 2
        cy = p["y"] + p["h"] // 2
        sid = winding_sector(cx + 0.5, cy + 0.5, verts, sidedefs, linedefs, sectors)
        parent = id_map.get(p.get("in_room"))
        if sid != parent:
            print(f"  PROP_VOID {p['type']}@{p['x']},{p['y']} sid={sid} want={parent}")
            fails += 1

    # critical path
    pts = []
    for th in layout["things"]:
        if th["type"] == "Player1Start":
            pts.append(("spawn", th["x"], th["y"]))
    for r in expanded["rooms"]:
        x0, y0, x1, y1 = _room_bounds(r)
        if r.get("_synthetic") and not r.get("_closet_release"):
            pts.append((f"corr:{r['id']}", (x0 + x1) // 2, (y0 + y1) // 2))
        elif not r.get("_synthetic") and not r.get("_closet"):
            cx = int(r["x"]) + int(r["w"]) // 2
            cy = int(r["y"]) + int(r["h"]) // 2
            for p in layout.get("props", []):
                rh = p.get("floor_raise", 96 if p["type"] == "pillar" else 32)
                if not (p["type"] == "pillar" or rh > 24):
                    continue
                if (
                    p.get("in_room") == r["id"]
                    and p["x"] - 8 <= cx <= p["x"] + p["w"] + 8
                    and p["y"] - 8 <= cy <= p["y"] + p["h"] + 8
                ):
                    cx, cy = int(r["x"]) + 24, int(r["y"]) + 24
                    break
            pts.append((f"room:{r['id']}", cx, cy))

    for label, x, y in pts:
        sid = winding_sector(x + 0.5, y + 0.5, verts, sidedefs, linedefs, sectors)
        if sid is None:
            print(f"  VOID {label} ({x},{y})")
            fails += 1
        elif label.startswith("corr:") and near_block(x, y, segs, 16):
            print(f"  BLOCKED {label} ({x},{y})")
            fails += 1

    # portal accidental blocking (diff-sector only)
    for i, ld in enumerate(linedefs):
        if not (ld.get("twosided") and ld.get("blocking")):
            continue
        sf = sidedefs[ld["sidefront"]]["sector"]
        sb = sidedefs[ld["sideback"]]["sector"]
        if sf != sb:
            print(f"  PORTAL_BLOCKING LD{i} sectors {sf}/{sb}")
            fails += 1

    fails += audit_portal_punches(name, layout, expanded, verts, sidedefs, linedefs)

    print(f"  {'PASS' if fails == 0 else 'FAIL'} ({fails} issues)")
    return fails


def _ld_span(ld, verts):
    x1, y1 = verts[ld["v1"]]["x"], verts[ld["v1"]]["y"]
    x2, y2 = verts[ld["v2"]]["x"], verts[ld["v2"]]["y"]
    if y1 == y2:
        return ("h", y1, min(x1, x2), max(x1, x2))
    if x1 == x2:
        return ("v", x1, min(y1, y2), max(y1, y2))
    return None


def audit_portal_punches(name, layout, expanded, verts, sidedefs, linedefs) -> int:
    """Detect incomplete wall punches: portal width gaps, coplanar one-sided
    walls overlapping a portal XY span, door/lift linedefs with a sibling wall
    still blocking the same span.
    """
    fails = 0
    rooms = {r["id"]: r for r in expanded["rooms"]}
    corridors = [r for r in expanded["rooms"] if r.get("_synthetic")]
    conns = layout.get("connections", [])

    # Index linedefs by axis line
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

    # 1) Coplanar one-sided wall overlapping any two-sided portal span
    for key, segs in by_axis.items():
        portals = [s for s in segs if not s["one"]]
        walls = [s for s in segs if s["one"]]
        for p in portals:
            for w in walls:
                olo, ohi = max(p["lo"], w["lo"]), min(p["hi"], w["hi"])
                if ohi > olo:
                    print(
                        f"  PORTAL_WALL_OVERLAP {key} portal LD{p['i']} "
                        f"[{p['lo']},{p['hi']}] vs wall LD{w['i']} "
                        f"[{w['lo']},{w['hi']}] overlap={ohi - olo}"
                    )
                    fails += 1

    # 2) Connection width vs actual two-sided gap on the parent face
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
        # Determine attach face on room a
        ax0, ay0, ax1, ay1 = _room_bounds(a)
        if corr.get("_portal_left") == a["id"] and cx0 == ax1:
            orient, const, glo, ghi = "v", ax1, cy0, cy1
            parent = a
            side = "right"
        elif corr.get("_portal_right") == a["id"] and cx1 == ax0:
            orient, const, glo, ghi = "v", ax0, cy0, cy1
            parent = a
            side = "left"
        elif corr.get("_portal_bottom") == a["id"] and cy0 == ay1:
            orient, const, glo, ghi = "h", ay1, cx0, cx1
            parent = a
            side = "top"
        elif corr.get("_portal_top") == a["id"] and cy1 == ay0:
            orient, const, glo, ghi = "h", ay0, cx0, cx1
            parent = a
            side = "bottom"
        else:
            # try room b as parent face
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
                print(f"  PORTAL_UNATTACHED {cid}")
                fails += 1
                continue

        gap = ghi - glo
        # Corridor must sit on real outline span
        span = _side_span_at(parent, side, const)
        if not span or glo < span[0] - 0.1 or ghi > span[1] + 0.1:
            print(
                f"  PORTAL_PAST_EDGE {cid} {side}@{const} "
                f"corr[{glo},{ghi}] edge={span}"
            )
            fails += 1

        # Sum two-sided coverage on this face overlapping the corridor span
        covered = 0
        segs = by_axis.get((orient, const), [])
        for s in segs:
            if s["one"]:
                continue
            olo, ohi = max(glo, s["lo"]), min(ghi, s["hi"])
            if ohi > olo:
                covered += ohi - olo
        if covered < gap - 1:
            print(
                f"  PORTAL_INCOMPLETE_PUNCH {cid} want_gap={gap} "
                f"twosided_cover={covered} conn_width={want}"
            )
            fails += 1
        # Door/lift: any one-sided sibling still covering the portal span
        if corr.get("_door") or corr.get("_lift"):
            for s in segs:
                if not s["one"]:
                    continue
                olo, ohi = max(glo, s["lo"]), min(ghi, s["hi"])
                if ohi > olo:
                    print(
                        f"  DOOR_SIBLING_WALL {cid} LD{s['i']} "
                        f"blocks [{olo},{ohi}] of portal [{glo},{ghi}]"
                    )
                    fails += 1

    # 3) Flush-to-corner opening on a short L face (half-door appearance)
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
                # opening on this exact edge segment
                if not (h0 >= elo and h1 <= ehi):
                    continue
                # Must match const via openings only applied on aabb face in emit;
                # approximate: opening interval overlaps this edge.
                flush = h0 == elo or h1 == ehi
                frac = (h1 - h0) / edge_len
                if flush and 0.3 <= frac <= 0.7:
                    # Confirm opening is on this const by checking side span
                    span = _side_span_at(room, side, const)
                    if span and span[0] == elo and span[1] == ehi:
                        print(
                            f"  HALF_PORTAL_APPEARANCE {room['id']} {side}@{const} "
                            f"edge[{elo},{ehi}] open[{h0},{h1}] flush"
                        )
                        fails += 1

    return fails


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "maps",
        nargs="*",
        default=["brine_pump_station", "nuclear_plant_v0"],
    )
    args = p.parse_args()
    total = sum(audit(m) for m in args.maps)
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
