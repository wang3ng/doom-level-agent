"""Training pack: verified SFT + idgames comment ingest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.validate import validate_layout
from train.comments import critic_target, tag_pillars
from train.idgames import (
    FileRecord,
    Review,
    fetch_frontend_page,
    parse_api_get,
    parse_idgames_page,
    sanitize_file,
)
from train.pack import build_pack, write_pack
from train.sft import load_jsonl
from train.verified import load_passing_layouts


def test_parse_fixture_markdown():
    md = (ROOT / "data" / "train" / "fixtures" / "pages" / "trouble.md").read_text(
        encoding="utf-8"
    )
    rec = parse_idgames_page(md)
    assert rec.title == "Trouble on Titan"
    assert rec.filename == "trouble.zip"
    assert rec.dir == "levels/doom2/s-u/"
    assert rec.id == 12444
    assert rec.votes == 12
    assert len(rec.reviews) >= 2
    assert "fun" in rec.reviews[0].text.lower()


def test_fetch_frontend_with_opener():
    md = (ROOT / "data" / "train" / "fixtures" / "pages" / "trouble.md").read_text(
        encoding="utf-8"
    )
    rec = fetch_frontend_page(
        "levels/doom2/s-u/trouble",
        opener=lambda _url: md,
    )
    assert rec.title == "Trouble on Titan"
    assert rec.id == 12444
    assert len(rec.reviews) >= 2


def test_sanitize_strips_email():
    rec = sanitize_file(
        FileRecord(
            title="x",
            filename="x.zip",
            author="A <mapper@example.com>",
            description="mail me at mapper@example.com please",
            reviews=[Review(username="bob", text="cool mapper@example.com 5/5", vote=None)],
        )
    )
    blob = rec.author + rec.description + rec.reviews[0].text
    assert "@" not in blob
    assert rec.reviews[0].vote == 5


def test_api_get_parse():
    payload = {
        "content": {
            "id": 15156,
            "title": "Community Chest 3",
            "dir": "levels/doom2/Ports/megawads/",
            "filename": "cchest3.zip",
            "author": "Various",
            "email": "secret@example.com",
            "description": "A 32-map megawad.",
            "rating": 4.2,
            "votes": 99,
            "url": "https://www.doomworld.com/idgames/index.php?id=15156",
            "reviews": {
                "review": [
                    {"username": "Anon", "text": "Got lost after the hub.", "vote": 2},
                    {"username": None, "text": "Great landmark in the plant core.", "vote": 5},
                ]
            },
        }
    }
    rec = parse_api_get(payload)
    assert rec.id == 15156
    assert rec.rating == 4.2
    assert len(rec.reviews) == 2
    assert rec.reviews[0].vote == 2
    tagged = tag_pillars(rec.reviews[0].text)
    assert "navigation" in tagged
    target = critic_target(rec.reviews[0], rec)
    assert target["severity"] == "playability"
    assert target["lessons"]
    avoid = critic_target(Review(username="a", text="It's not fun.", vote=1), rec)
    assert avoid["lessons"][0].startswith("Avoid")


def test_verified_layouts_are_valid():
    layouts = load_passing_layouts(ROOT)
    names = {n for n, _ in layouts}
    assert "brine_pump_station" in names
    assert "nuclear_plant_v0" in names
    for _, layout in layouts:
        assert validate_layout(layout) == []


def test_pack_writes_jsonl(tmp_path: Path):
    records = build_pack(root=ROOT)
    assert len(records) >= 20
    sources = {r.source for r in records}
    tasks = {r.task for r in records}
    assert "verified" in sources and "community" in sources
    assert "layout" in tasks and "critic" in tasks
    layout_rec = next(r for r in records if r.task == "layout" and "brine" in r.id)
    body = json.loads(layout_rec.messages[-1]["content"])
    assert body["name"] == "brine_pump_station"
    pillar = next(p for p in body["props"] if p["type"] == "pillar")
    assert (pillar["x"], pillar["y"]) == (720, 300)

    out = tmp_path / "sft.jsonl"
    stats = write_pack(records, jsonl_path=out)
    assert out.is_file()
    rows = load_jsonl(out)
    assert len(rows) == stats["n"] == len(records)
    lessons = json.loads((tmp_path / "community_lessons.json").read_text())
    assert lessons
    assert all("@" not in json.dumps(row) for row in rows)


def test_lessons_selector():
    from corpus.lessons import format_lessons_block, select_lessons

    lessons = [
        "Avoid: dark cavern maze at the start.",
        "Keep: hub landmark readable.",
        "Avoid: yellow key door that instakills.",
    ]
    picked = select_lessons("yellow key hub", k=2, lessons=lessons)
    assert picked[0].lower().find("hub") >= 0 or "yellow" in picked[0].lower()
    block = format_lessons_block("maze", k=2)
    assert isinstance(block, str)


if __name__ == "__main__":
    test_parse_fixture_markdown()
    test_fetch_frontend_with_opener()
    test_sanitize_strips_email()
    test_api_get_parse()
    test_verified_layouts_are_valid()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as d:
        test_pack_writes_jsonl(Path(d))
    test_lessons_selector()
    print("ok")
