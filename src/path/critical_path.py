"""Critical-path extraction for classic WADs and DoomLayoutV0 JSON."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from wad.classic import (
    EXIT_SPECIALS,
    KEY_COLOR,
    KEY_TYPES,
    LOCKED_SPECIALS,
    ML_BLOCKING,
    NO_SIDE,
    PLAYER1_START,
    ClassicMap,
    load_classic_map,
)


def _point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    """Ray cast; ring is list of vertices (not necessarily closed)."""
    if len(ring) < 3:
        return False
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def _sector_polygons(m: ClassicMap) -> dict[int, list[tuple[float, float]]]:
    """Approximate each sector as an unordered edge soup → ordered cycle (best effort)."""
    edges: dict[int, list[tuple[tuple[int, int], tuple[int, int]]]] = defaultdict(list)
    for ld in m.linedefs:
        v1 = (m.vertices[ld.v1].x, m.vertices[ld.v1].y)
        v2 = (m.vertices[ld.v2].x, m.vertices[ld.v2].y)
        for side_i in (ld.side_front, ld.side_back):
            if side_i == NO_SIDE or side_i >= len(m.sidedefs):
                continue
            sec = m.sidedefs[side_i].sector
            edges[sec].append((v1, v2))

    polys: dict[int, list[tuple[float, float]]] = {}
    for sec, edgelist in edges.items():
        # Walk a single cycle from the edge list (works for simple sectors).
        adj: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for a, b in edgelist:
            adj[a].append(b)
            adj[b].append(a)
        if not adj:
            continue
        start = next(iter(adj))
        ring = [start]
        prev = None
        cur = start
        for _ in range(len(edgelist) + 2):
            nbrs = [n for n in adj[cur] if n != prev]
            if not nbrs:
                break
            nxt = nbrs[0]
            if nxt == start:
                break
            ring.append(nxt)
            prev, cur = cur, nxt
        polys[sec] = [(float(x), float(y)) for x, y in ring]
    return polys


def sector_at_point(m: ClassicMap, x: int, y: int, polys: dict[int, list[tuple[float, float]]] | None = None) -> int | None:
    polys = polys or _sector_polygons(m)
    hits = [s for s, ring in polys.items() if _point_in_ring(x, y, ring)]
    if not hits:
        # fallback: nearest sector centroid
        best, best_d = None, float("inf")
        for s, ring in polys.items():
            if not ring:
                continue
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            d = (cx - x) ** 2 + (cy - y) ** 2
            if d < best_d:
                best, best_d = s, d
        return best
    if len(hits) == 1:
        return hits[0]
    # prefer smallest area proxy
    def area(s: int) -> float:
        ring = polys[s]
        a = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            a += x1 * y2 - x2 * y1
        return abs(a)

    return min(hits, key=area)


def build_sector_graph(m: ClassicMap) -> dict[int, list[dict[str, Any]]]:
    """Undirected sector adjacency with lock/exit metadata on edges."""
    graph: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, ld in enumerate(m.linedefs):
        if ld.side_front == NO_SIDE or ld.side_front >= len(m.sidedefs):
            continue
        front = m.sidedefs[ld.side_front].sector
        back = None
        if ld.side_back != NO_SIDE and ld.side_back < len(m.sidedefs):
            back = m.sidedefs[ld.side_back].sector
        if back is None or back == front:
            continue
        if ld.flags & ML_BLOCKING:
            # impassable two-sided (fence/window)
            continue
        lock = LOCKED_SPECIALS.get(ld.special)
        edge = {
            "to": back,
            "linedef": i,
            "special": ld.special,
            "lock": lock,
            "is_exit": ld.special in EXIT_SPECIALS,
        }
        rev = {
            "to": front,
            "linedef": i,
            "special": ld.special,
            "lock": lock,
            "is_exit": ld.special in EXIT_SPECIALS,
        }
        graph[front].append(edge)
        graph[back].append(rev)
    return graph


def extract_critical_path_from_wad(path: str | Any, map_name: str | None = None) -> dict[str, Any]:
    m = load_classic_map(path, map_name=map_name) if not isinstance(path, ClassicMap) else path
    polys = _sector_polygons(m)
    graph = build_sector_graph(m)

    starts = [t for t in m.things if t.type == PLAYER1_START]
    if not starts:
        return {"ok": False, "error": "no Player1Start", "map": m.name}
    start_thing = starts[0]
    start_sec = sector_at_point(m, start_thing.x, start_thing.y, polys)
    if start_sec is None:
        return {"ok": False, "error": "could not locate start sector", "map": m.name}

    # Keys lying in sectors
    keys_in_sector: dict[int, set[str]] = defaultdict(set)
    for t in m.things:
        if t.type not in KEY_TYPES:
            continue
        sec = sector_at_point(m, t.x, t.y, polys)
        if sec is not None:
            keys_in_sector[sec].add(KEY_COLOR[KEY_TYPES[t.type]])

    exit_sectors: set[int] = set()
    for ld in m.linedefs:
        if ld.special not in EXIT_SPECIALS:
            continue
        if ld.side_front != NO_SIDE and ld.side_front < len(m.sidedefs):
            exit_sectors.add(m.sidedefs[ld.side_front].sector)
        if ld.side_back != NO_SIDE and ld.side_back < len(m.sidedefs):
            exit_sectors.add(m.sidedefs[ld.side_back].sector)

    # State-space BFS: (sector, frozenset colors)
    start_keys = frozenset(keys_in_sector.get(start_sec, ()))
    q = deque([(start_sec, start_keys)])
    parent: dict[tuple[int, frozenset], tuple[tuple[int, frozenset], dict[str, Any] | None]] = {
        (start_sec, start_keys): ((start_sec, start_keys), None)
    }
    goal_state = None
    while q:
        sec, keys = q.popleft()
        if sec in exit_sectors:
            goal_state = (sec, keys)
            break
        # pick up keys in this sector (already merged on entry)
        for e in graph.get(sec, []):
            need = e["lock"]
            if need and need not in keys:
                continue
            nxt_sec = e["to"]
            nxt_keys = keys | frozenset(keys_in_sector.get(nxt_sec, ()))
            st = (nxt_sec, nxt_keys)
            if st in parent:
                continue
            parent[st] = ((sec, keys), e)
            q.append(st)

    if goal_state is None:
        # fallback: longest reachable path as "exploration path"
        farthest = max(parent.keys(), key=lambda s: _depth(parent, s))
        goal_state = farthest
        reached_exit = False
    else:
        reached_exit = True

    chain = _reconstruct(parent, goal_state)
    sectors_path = [s for s, _k in chain]
    locks_used = []
    for i in range(1, len(chain)):
        _prev, edge = parent[chain[i]]
        if edge and edge.get("lock"):
            locks_used.append({"from": chain[i - 1][0], "to": chain[i][0], "key": edge["lock"]})

    n_sec = max(len(m.sectors), 1)
    unique_secs = len(set(sectors_path))
    branch = sum(len(graph[s]) for s in set(sectors_path)) / max(unique_secs, 1)

    return {
        "ok": True,
        "source": "classic_wad",
        "map": m.name,
        "reached_exit": reached_exit,
        "start_sector": start_sec,
        "goal_sector": goal_state[0],
        "start_xy": {"x": start_thing.x, "y": start_thing.y},
        "path_sectors": sectors_path,
        "path_length": len(sectors_path),
        "unique_sectors_on_path": unique_secs,
        "keys_collected": sorted(goal_state[1]),
        "locks_used": locks_used,
        "n_sectors_total": len(m.sectors),
        "coverage": round(unique_secs / n_sec, 3),
        "avg_branching_on_path": round(branch, 3),
        "exit_sector_count": len(exit_sectors),
        "key_things": [
            {"type": KEY_TYPES[t.type], "x": t.x, "y": t.y} for t in m.things if t.type in KEY_TYPES
        ],
    }


def _depth(parent: dict, state: tuple) -> int:
    d = 0
    cur = state
    seen = set()
    while cur in parent and parent[cur][1] is not None and cur not in seen:
        seen.add(cur)
        cur = parent[cur][0]
        d += 1
    return d


def _reconstruct(parent: dict, goal: tuple) -> list[tuple]:
    chain = [goal]
    cur = goal
    seen = set()
    while cur in parent and parent[cur][1] is not None and cur not in seen:
        seen.add(cur)
        cur = parent[cur][0]
        chain.append(cur)
    chain.reverse()
    return chain


def extract_critical_path_from_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Room-graph critical path for DoomLayoutV0 JSON."""
    rooms = {r["id"]: r for r in layout.get("rooms", [])}
    if not rooms:
        return {"ok": False, "error": "no rooms"}

    # assign things to rooms
    def in_room(x: int, y: int, r: dict[str, Any]) -> bool:
        return int(r["x"]) <= x < int(r["x"]) + int(r["w"]) and int(r["y"]) <= y < int(r["y"]) + int(r["h"])

    start = None
    for th in layout.get("things", []):
        if th.get("type") == "Player1Start":
            for rid, r in rooms.items():
                if in_room(int(th["x"]), int(th["y"]), r):
                    start = rid
                    break
    if start is None:
        start = next(iter(rooms))

    goal = layout.get("objective_room")
    if not goal:
        for th in layout.get("things", []):
            if th.get("type") == "ExitSwitch":
                for rid, r in rooms.items():
                    if in_room(int(th["x"]), int(th["y"]), r):
                        goal = rid
                        break
    if not goal:
        # farthest room from start in hops, prefer room with monsters
        adj: dict[str, list[str]] = defaultdict(list)
        for c in layout.get("connections", []):
            if c["a"] in rooms and c["b"] in rooms:
                adj[c["a"]].append(c["b"])
                adj[c["b"]].append(c["a"])
        dist = {start: 0}
        q = deque([start])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        goal = max(dist, key=lambda r: (dist[r], sum(1 for t in layout.get("things", []) if t.get("type") in {"Imp", "Zombieman", "ShotgunGuy"} and in_room(int(t["x"]), int(t["y"]), rooms[r]))))

    adj2: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in layout.get("connections", []):
        if c["a"] in rooms and c["b"] in rooms:
            adj2[c["a"]].append({"to": c["b"], **c})
            adj2[c["b"]].append({"to": c["a"], **c})

    keys_in_room: dict[str, set[str]] = defaultdict(set)
    for th in layout.get("things", []):
        color = {
            "BlueCard": "blue",
            "YellowCard": "yellow",
            "RedCard": "red",
        }.get(th.get("type"))
        if not color:
            continue
        for rid, r in rooms.items():
            if in_room(int(th["x"]), int(th["y"]), r):
                keys_in_room[rid].add(color)
                break

    start_keys = frozenset(keys_in_room.get(start, ()))
    qk: deque[tuple[str, frozenset[str]]] = deque([(start, start_keys)])
    parent_state: dict[tuple[str, frozenset[str]], tuple[tuple[str, frozenset[str]], dict[str, Any] | None]] = {
        (start, start_keys): ((start, start_keys), None)
    }
    goal_state: tuple[str, frozenset[str]] | None = None
    while qk:
        u, keys = qk.popleft()
        if u == goal:
            goal_state = (u, keys)
            break
        for e in adj2[u]:
            need = e.get("lock")
            if need and need not in keys:
                continue
            v = e["to"]
            nxt_keys = keys | frozenset(keys_in_room.get(v, ()))
            st = (v, nxt_keys)
            if st in parent_state:
                continue
            parent_state[st] = ((u, keys), e)
            qk.append(st)

    if goal_state is None:
        return {"ok": False, "error": "goal unreachable (check keys/locks)", "start": start, "goal": goal}

    path_states: list[tuple[str, frozenset[str]]] = []
    locks_used: list[dict[str, Any]] = []
    st: tuple[str, frozenset[str]] | None = goal_state
    while st is not None:
        path_states.append(st)
        prev, edge = parent_state[st]
        if edge is None:
            break
        if edge.get("lock"):
            locks_used.append({"from": prev[0], "to": st[0], "key": edge["lock"]})
        st = prev
    path_states.reverse()
    locks_used.reverse()
    path = [s[0] for s in path_states]

    return {
        "ok": True,
        "source": "layout_json",
        "map": layout.get("name"),
        "reached_exit": goal == layout.get("objective_room") or any(
            t.get("type") == "ExitSwitch" for t in layout.get("things", [])
        ),
        "start_room": start,
        "goal_room": goal,
        "path_rooms": path,
        "path_length": len(path),
        "unique_rooms_on_path": len(set(path)),
        "n_rooms_total": len(rooms),
        "coverage": round(len(set(path)) / max(len(rooms), 1), 3),
        "avg_branching_on_path": round(
            sum(len(adj2[r]) for r in set(path)) / max(len(set(path)), 1), 3
        ),
        "keys_collected": sorted(goal_state[1]),
        "locks_used": locks_used,
    }


def score_critical_path(path_report: dict[str, Any]) -> dict[str, Any]:
    """0–5 clarity score: exists, reaches exit, gated progression, not a pure line or spaghetti."""
    if not path_report.get("ok"):
        return {
            "score": 0.5,
            "method": "critical_path",
            "notes": path_report.get("error", "path extract failed"),
            "evidence": path_report,
        }
    score = 1.0
    notes = []
    if path_report.get("reached_exit"):
        score += 1.25
        notes.append("reaches exit")
    else:
        notes.append("no exit reached (exploration path only)")

    length = path_report.get("path_length") or path_report.get("path_rooms") and len(path_report["path_rooms"]) or 0
    total = path_report.get("n_sectors_total") or path_report.get("n_rooms_total") or 1
    cov = float(path_report.get("coverage") or 0)
    if length >= 4:
        score += 0.75
        notes.append(f"path length {length}")
    elif length >= 2:
        score += 0.35
        notes.append(f"short path length {length}")
    else:
        notes.append("trivial path")

    if path_report.get("locks_used") or path_report.get("keys_collected"):
        score += 0.75
        notes.append("key gating on critical path")
    branch = float(path_report.get("avg_branching_on_path") or 0)
    if 1.5 <= branch <= 4.0:
        score += 0.5
        notes.append(f"moderate branching {branch:.2f}")
    elif branch > 4.0:
        score += 0.15
        notes.append(f"high branching {branch:.2f} (noisy)")
    else:
        notes.append(f"line-like branching {branch:.2f}")

    if 0.25 <= cov <= 0.85:
        score += 0.5
        notes.append(f"coverage {cov:.2f}")
    elif cov > 0.85:
        score += 0.2
        notes.append(f"very high coverage {cov:.2f}")

    score = max(0.0, min(5.0, score))
    return {
        "score": round(score, 3),
        "method": "critical_path",
        "notes": "; ".join(notes),
        "evidence": {
            "path_length": length,
            "coverage": cov,
            "reached_exit": path_report.get("reached_exit"),
            "keys": path_report.get("keys_collected"),
        },
    }
