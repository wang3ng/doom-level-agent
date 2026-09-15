"""Deterministic JSON layout -> UDMF TEXTMAP (+ minimal PWAD)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# DoomEd numbers (Doom 2 / compatible commons)
THING_ED_NUMBERS = {
    "Player1Start": 1,
    "Zombieman": 3004,
    "ShotgunGuy": 9,
    "Imp": 3001,
    "HealthBonus": 2014,
    "Clip": 2007,
    "Shotgun": 2001,
    "ArmorBonus": 2015,
    "ExitSwitch": 1,  # placeholder; exit handled via linedef special later
}

DEFAULT_WALL = "STONE2"


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


def _rect_vertices(x: int, y: int, w: int, h: int) -> list[Vertex]:
    # CCW: SW, SE, NE, NW
    return [
        Vertex(x, y),
        Vertex(x + w, y),
        Vertex(x + w, y + h),
        Vertex(x, y + h),
    ]


def layout_to_udmf(layout: dict[str, Any]) -> str:
    """Build a simple UDMF map: one sector per room (no shared walls yet).

    Mid-prototype: rooms are independent rectangles. Connections are recorded
    in comments / future corridor stitching; playable maps need overlapping or
    corridor rooms in the JSON for now.
    """
    vertices: list[Vertex] = []
    linedefs: list[dict[str, Any]] = []
    sidedefs: list[dict[str, Any]] = []
    sectors: list[Sector] = []
    things: list[dict[str, Any]] = []

    room_index = {r["id"]: i for i, r in enumerate(layout["rooms"])}

    for room in layout["rooms"]:
        sid = len(sectors)
        sectors.append(
            Sector(
                floor_height=int(room.get("floor_height", 0)),
                ceiling_height=int(room.get("ceiling_height", 128)),
                floor_flat=room.get("floor_flat", "FLOOR0_1"),
                ceil_flat=room.get("ceil_flat", "CEIL1_1"),
                light=int(room.get("light", 160)),
            )
        )
        base = len(vertices)
        verts = _rect_vertices(room["x"], room["y"], room["w"], room["h"])
        vertices.extend(verts)
        # four edges: 0-1, 1-2, 2-3, 3-0
        for i in range(4):
            v1 = base + i
            v2 = base + ((i + 1) % 4)
            sd = len(sidedefs)
            sidedefs.append(
                {
                    "sector": sid,
                    "texturemiddle": DEFAULT_WALL,
                }
            )
            linedefs.append(
                {
                    "v1": v1,
                    "v2": v2,
                    "sidefront": sd,
                    "blocking": True,
                }
            )

    # Optional: mark connections in a comment block for stage-2 debugging
    conn_lines = []
    for c in layout.get("connections", []):
        if c["a"] in room_index and c["b"] in room_index:
            conn_lines.append(
                f"// connection {c['a']} -> {c['b']} kind={c.get('kind', 'open')} width={c.get('width', 64)}"
            )

    for th in layout.get("things", []):
        tname = th["type"]
        ed = THING_ED_NUMBERS.get(tname, 1)
        if tname == "ExitSwitch":
            continue  # skip until linedef exit specials exist
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

    lines: list[str] = [
        "namespace = \"zdoom\";",
        f"// map: {layout.get('name', 'MAP01')}",
        f"// theme: {layout.get('theme', '')}",
    ]
    lines.extend(conn_lines)

    for i, v in enumerate(vertices):
        lines.append(f"vertex // {i}")
        lines.append("{")
        lines.append(f"  x = {v.x}.000;")
        lines.append(f"  y = {v.y}.000;")
        lines.append("}")

    for i, s in enumerate(sectors):
        lines.append(f"sector // {i}")
        lines.append("{")
        lines.append(f"  heightfloor = {s.floor_height};")
        lines.append(f"  heightceiling = {s.ceiling_height};")
        lines.append(f"  texturefloor = \"{s.floor_flat}\";")
        lines.append(f"  textureceiling = \"{s.ceil_flat}\";")
        lines.append(f"  lightlevel = {s.light};")
        lines.append("}")

    for i, sd in enumerate(sidedefs):
        lines.append(f"sidedef // {i}")
        lines.append("{")
        lines.append(f"  sector = {sd['sector']};")
        lines.append(f"  texturemiddle = \"{sd['texturemiddle']}\";")
        lines.append("}")

    for i, ld in enumerate(linedefs):
        lines.append(f"linedef // {i}")
        lines.append("{")
        lines.append(f"  v1 = {ld['v1']};")
        lines.append(f"  v2 = {ld['v2']};")
        lines.append(f"  sidefront = {ld['sidefront']};")
        if ld.get("blocking"):
            lines.append("  blocking = true;")
        lines.append("}")

    for i, th in enumerate(things):
        lines.append(f"thing // {i}")
        lines.append("{")
        for k, v in th.items():
            if isinstance(v, bool):
                lines.append(f"  {k} = {'true' if v else 'false'};")
            elif isinstance(v, str):
                lines.append(f"  {k} = \"{v}\";")
            else:
                lines.append(f"  {k} = {v};")
        lines.append("}")

    return "\n".join(lines) + "\n"


def _lump(name: str, data: bytes) -> tuple[bytes, bytes]:
    """Return (directory entry 16 bytes, payload)."""
    name_b = name.encode("ascii")[:8].ljust(8, b"\x00")
    return name_b, data


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

    # PWAD header + lump payloads + directory
    header_size = 12
    payloads: list[bytes] = []
    directory = bytearray()
    offset = header_size
    for name, data in lumps:
        payloads.append(data)
        # dir entry: filepos(4) size(4) name(8)
        directory += struct.pack("<II", offset, len(data))
        directory += name.encode("ascii")[:8].ljust(8, b"\x00")
        offset += len(data)

    num_lumps = len(lumps)
    info_table_ofs = offset
    header = b"PWAD" + struct.pack("<II", num_lumps, info_table_ofs)

    with out_path.open("wb") as f:
        f.write(header)
        for p in payloads:
            f.write(p)
        f.write(directory)

    # Also drop a raw .txt next to it for UDB/debug
    txt_path = out_path.with_suffix(".txt")
    txt_path.write_text(udmf_text, encoding="utf-8")
    return out_path
