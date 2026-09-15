"""Stage 3: validated layout JSON -> UDMF PWAD for UDB / GZDoom."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.validate import connectivity_ok, validate_layout  # noqa: E402
from udmf.writer import layout_to_udmf, write_textmap_wad  # noqa: E402


def build_map(layout: dict[str, Any], out_wad: Path) -> Path:
    errors = validate_layout(layout)
    if errors:
        raise ValueError("layout invalid:\n- " + "\n- ".join(errors))
    if not connectivity_ok(layout):
        raise ValueError("layout rooms are not fully connected")
    udmf = layout_to_udmf(layout)
    return write_textmap_wad(udmf, out_wad, map_name="MAP01")


def build_from_json_file(layout_path: Path, out_wad: Path) -> Path:
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    return build_map(layout, out_wad)
