import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.stage3_build import build_map
from pipeline.validate import connectivity_ok, validate_layout
from udmf.writer import layout_to_udmf


def test_proto_layout_builds(tmp_path=None):
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_two_rooms.json").read_text(encoding="utf-8")
    )
    assert validate_layout(layout) == []
    assert connectivity_ok(layout)
    udmf = layout_to_udmf(layout)
    assert 'namespace = "zdoom";' in udmf
    assert "vertex" in udmf and "sector" in udmf
    out = (tmp_path or (ROOT / "data" / "maps")) / "test_MAP01.wad"
    out = Path(out)
    wad = build_map(layout, out)
    assert wad.exists() and wad.stat().st_size > 16


if __name__ == "__main__":
    test_proto_layout_builds()
    print("ok")
