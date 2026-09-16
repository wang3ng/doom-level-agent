import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from critic.scorer import score_layout


def test_proto_scores_are_conservative():
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_techbase_v1.json").read_text(encoding="utf-8")
    )
    report = score_layout(layout)
    overall = report["summary"]["overall"]
    with_gaps = report["summary"]["overall_with_gaps"]
    assert overall is not None
    # A tiny prototype must not look near-perfect on heuristics alone.
    assert overall < 3.2
    assert with_gaps < overall
    assert report["summary"]["n_scored"] >= 10
    by = {c["criterion"]: c for c in report["criteria"]}
    assert by["subversion"]["score"] is None
    assert by["showing_vs_telling"]["score"] is None
    for c in report["criteria"]:
        if c["method"] == "heuristic" and c["score"] is not None:
            cap = 2.5 if c["needs_vision"] else 3.5
            assert c["score"] <= cap + 1e-6


def test_annotation_override():
    layout = json.loads(
        (ROOT / "data" / "layouts" / "proto_two_rooms.json").read_text(encoding="utf-8")
    )
    report = score_layout(
        layout,
        annotations={
            "mechanic_utilization": {
                "subversion": {"score": 4, "notes": "door reused as trap at end"}
            }
        },
    )
    by = {c["criterion"]: c for c in report["criteria"]}
    assert by["subversion"]["score"] == 4.0
    assert by["subversion"]["method"] == "annotation"


if __name__ == "__main__":
    test_proto_scores_are_conservative()
    test_annotation_override()
    print("ok")
