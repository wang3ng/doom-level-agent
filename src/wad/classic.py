"""Parse classic (non-UDMF) Doom PWAD map lumps."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Lump:
    name: str
    data: bytes


@dataclass
class Thing:
    x: int
    y: int
    angle: int
    type: int
    flags: int


@dataclass
class Linedef:
    v1: int
    v2: int
    flags: int
    special: int
    tag: int
    side_front: int
    side_back: int


@dataclass
class Sidedef:
    xoff: int
    yoff: int
    tex_upper: str
    tex_lower: str
    tex_middle: str
    sector: int


@dataclass
class Vertex:
    x: int
    y: int


@dataclass
class Sector:
    floor_height: int
    ceiling_height: int
    floor_pic: str
    ceil_pic: str
    light: int
    special: int
    tag: int


@dataclass
class ClassicMap:
    name: str
    things: list[Thing] = field(default_factory=list)
    linedefs: list[Linedef] = field(default_factory=list)
    sidedefs: list[Sidedef] = field(default_factory=list)
    vertices: list[Vertex] = field(default_factory=list)
    sectors: list[Sector] = field(default_factory=list)


def _iname(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def read_wad_lumps(path: Path | str) -> list[Lump]:
    data = Path(path).read_bytes()
    if data[:4] not in (b"PWAD", b"IWAD"):
        raise ValueError(f"Not a WAD: {path}")
    n, info = struct.unpack_from("<II", data, 4)
    lumps: list[Lump] = []
    for i in range(n):
        off, size = struct.unpack_from("<II", data, info + i * 16)
        name = _iname(data[info + i * 16 + 8 : info + i * 16 + 16])
        lumps.append(Lump(name=name, data=data[off : off + size]))
    return lumps


def _is_map_marker(name: str) -> bool:
    if name.startswith("MAP") and len(name) >= 5:
        return True
    return len(name) == 4 and name[0] == "E" and name[2] == "M" and name[1].isdigit() and name[3].isdigit()


def load_classic_map(path: Path | str, map_name: str | None = None) -> ClassicMap:
    lumps = read_wad_lumps(path)
    markers = [i for i, L in enumerate(lumps) if _is_map_marker(L.name) and L.data == b""]
    if not markers:
        raise ValueError(f"No map markers in {path}")
    start = markers[0]
    if map_name:
        found = [i for i in markers if lumps[i].name.upper() == map_name.upper()]
        if not found:
            raise ValueError(f"Map {map_name} not in {path}")
        start = found[0]

    by_name: dict[str, bytes] = {}
    for L in lumps[start + 1 :]:
        if _is_map_marker(L.name) and L.data == b"":
            break
        by_name[L.name] = L.data

    m = ClassicMap(name=lumps[start].name)
    th = by_name.get("THINGS", b"")
    for i in range(0, len(th), 10):
        x, y, ang, typ, flags = struct.unpack_from("<hhHHH", th, i)
        m.things.append(Thing(x, y, ang, typ, flags))

    ld = by_name.get("LINEDEFS", b"")
    for i in range(0, len(ld), 14):
        v1, v2, flags, special, tag, s1, s2 = struct.unpack_from("<HHHHHHH", ld, i)
        m.linedefs.append(Linedef(v1, v2, flags, special, tag, s1, s2))

    sd = by_name.get("SIDEDEFS", b"")
    for i in range(0, len(sd), 30):
        xoff, yoff = struct.unpack_from("<hh", sd, i)
        up = _iname(sd[i + 4 : i + 12])
        low = _iname(sd[i + 12 : i + 20])
        mid = _iname(sd[i + 20 : i + 28])
        sec = struct.unpack_from("<H", sd, i + 28)[0]
        m.sidedefs.append(Sidedef(xoff, yoff, up, low, mid, sec))

    vx = by_name.get("VERTEXES", b"")
    for i in range(0, len(vx), 4):
        x, y = struct.unpack_from("<hh", vx, i)
        m.vertices.append(Vertex(x, y))

    sc = by_name.get("SECTORS", b"")
    for i in range(0, len(sc), 26):
        fh, ch = struct.unpack_from("<hh", sc, i)
        fp = _iname(sc[i + 4 : i + 12])
        cp = _iname(sc[i + 12 : i + 20])
        light, special, tag = struct.unpack_from("<HHH", sc, i + 20)
        m.sectors.append(Sector(fh, ch, fp, cp, light, special, tag))

    return m


# Doom thing types
PLAYER1_START = 1
KEY_TYPES = {
    5: "blue_card",
    6: "yellow_card",
    13: "red_card",
    40: "blue_skull",
    39: "yellow_skull",
    38: "red_skull",
}
KEY_COLOR = {
    "blue_card": "blue",
    "blue_skull": "blue",
    "yellow_card": "yellow",
    "yellow_skull": "yellow",
    "red_card": "red",
    "red_skull": "red",
}

# Linedef specials that require a key color
LOCKED_SPECIALS: dict[int, str] = {
    26: "blue",
    27: "yellow",
    28: "red",
    32: "blue",
    33: "red",
    34: "yellow",
    99: "blue",
    133: "blue",
    134: "red",
    135: "red",
    136: "yellow",
    137: "yellow",
}

EXIT_SPECIALS = {11, 51, 52, 124, 197, 198}

ML_BLOCKING = 0x0001
ML_TWOSIDED = 0x0004
NO_SIDE = 0xFFFF


def summarize_map(m: ClassicMap) -> dict[str, Any]:
    return {
        "name": m.name,
        "n_things": len(m.things),
        "n_linedefs": len(m.linedefs),
        "n_sectors": len(m.sectors),
        "n_vertices": len(m.vertices),
        "player_starts": sum(1 for t in m.things if t.type == PLAYER1_START),
        "keys": [
            {"type": KEY_TYPES[t.type], "x": t.x, "y": t.y}
            for t in m.things
            if t.type in KEY_TYPES
        ],
        "exit_linedefs": sum(1 for ld in m.linedefs if ld.special in EXIT_SPECIALS),
    }
