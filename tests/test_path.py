import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from path.critical_path import (
    extract_critical_path_from_layout,
    extract_critical_path_from_wad,
    score_critical_path,
)
from path.describe import describe_from_path


def test_layout_path():
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_techbase_v1.json").read_text(encoding="utf-8")
    )
    report = extract_critical_path_from_layout(layout)
    assert report["ok"]
    assert report["path_rooms"][0] == report["start_room"]
    clarity = score_critical_path(report)
    assert 0 <= clarity["score"] <= 5
    desc = describe_from_path(report, path_score=clarity, offline=True)
    assert "brief" in desc and len(desc["brief"]) > 10


def test_wad_path_project1():
    wad = ROOT / "data" / "corpus" / "wads" / "Project1.wad"
    if not wad.is_file():
        print("skip Project1.wad missing")
        return
    report = extract_critical_path_from_wad(wad)
    assert report["ok"], report
    clarity = score_critical_path(report)
    assert clarity["score"] >= 0.5


if __name__ == "__main__":
    test_layout_path()
    test_wad_path_project1()
    print("ok")
