"""Hull gate must PASS before a WAD is emitted."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.hull_gate import audit_report, assert_hull_ok
from pipeline.stage3_build import build_map
from pipeline.validate import validate_layout


@pytest.mark.parametrize(
    "name",
    ["brine_pump_station", "nuclear_plant_v0", "proto_techbase_v1", "proto_two_rooms"],
)
def test_demo_layouts_pass_hull_gate(name: str):
    path = ROOT / "data" / "layouts" / f"{name}.json"
    if not path.exists():
        pytest.skip(f"missing {path}")
    layout = json.loads(path.read_text(encoding="utf-8"))
    report = audit_report(layout)
    assert report["ok"], report["issues"]


def test_build_refuses_prop_on_portal(tmp_path: Path):
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_two_rooms.json").read_text(encoding="utf-8")
    )
    # Drop a solid on the corridor approach between the two rooms.
    rooms = {r["id"]: r for r in layout["rooms"]}
    a = layout["rooms"][0]
    # Place cover straddling the east face center (typical portal).
    layout.setdefault("props", []).append(
        {
            "type": "cover_block",
            "x": a["x"] + a["w"] - 16,
            "y": a["y"] + a["h"] // 2 - 16,
            "w": 32,
            "h": 32,
            "floor_raise": 40,
            "in_room": a["id"],
            "design": "intentional midline blocker for test",
        }
    )
    out = tmp_path / "should_not_write.wad"
    with pytest.raises(ValueError, match="hull/walkability|PROP_ON_PORTAL"):
        build_map(layout, out)
    assert not out.exists()


def test_validate_flags_closet_overlap():
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_two_rooms.json").read_text(encoding="utf-8")
    )
    # Force a closet that overlaps the second room if rooms are adjacent-ish —
    # use huge closet on east of first room.
    r0 = layout["rooms"][0]
    layout["closets"] = [
        {
            "id": "bad_closet",
            "attach_room": r0["id"],
            "side": "east",
            "w": 400,
            "h": 400,
            "gap": 16,
        }
    ]
    errs = validate_layout(layout)
    assert any("CLOSET_ROOM_OVERLAP" in e or "OVERLAP" in e for e in errs)


if __name__ == "__main__":
    for n in ["brine_pump_station", "nuclear_plant_v0", "proto_techbase_v1", "proto_two_rooms"]:
        p = ROOT / "data" / "layouts" / f"{n}.json"
        if not p.exists():
            print("skip", n)
            continue
        r = audit_report(json.loads(p.read_text(encoding="utf-8")))
        print(n, "PASS" if r["ok"] else "FAIL", r["n_issues"])
        for i in r["issues"][:8]:
            print(" ", i)
