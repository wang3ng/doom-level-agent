"""Map idgames reviews onto the five-pillar critic and SFT chat records."""

from __future__ import annotations

from typing import Any

from .idgames import FileRecord, Review
from .sft import CRITIC_TASK, ChatRecord, dumps_json

CRITIC_SYSTEM = """You map Doom player comments onto the five design pillars
(navigation, pacing, mechanics, affordances, narrative).
Output ONLY JSON:
{
  "pillars": {
    "navigation": {"score": 0-5 or null, "notes": "..."},
    "pacing": {"score": 0-5 or null, "notes": "..."},
    "mechanics": {"score": 0-5 or null, "notes": "..."},
    "affordances": {"score": 0-5 or null, "notes": "..."},
    "narrative": {"score": 0-5 or null, "notes": "..."}
  },
  "lessons": ["short actionable layout rules for JSON→WAD Stage 2"],
  "severity": "playability" | "style" | "mixed",
  "keep": true
}
Scores: 5 rave, 3 mixed, 1 harsh. Null if the comment does not mention that pillar.
No markdown fences.
"""

PILLAR_TERMS: dict[str, tuple[str, ...]] = {
    "navigation": (
        "lost",
        "maze",
        "confusing",
        "hub",
        "backtrack",
        "layout",
        "rectangular",
        "cramped",
        "door",
        "path",
        "exit",
        "complex",
    ),
    "pacing": (
        "hard",
        "easy",
        "ammo",
        "weapon",
        "boring",
        "fun",
        "gameplay",
        "killed",
        "monster",
        "balance",
        "health",
        "not enough",
    ),
    "mechanics": (
        "key",
        "switch",
        "lock",
        "secret",
        "lift",
        "puzzle",
        "teleport",
        "popup",
        "closet",
        "trigger",
    ),
    "affordances": (
        "texture",
        "lighting",
        "look",
        "ugly",
        "detail",
        "sky",
        "door looks",
        "visual",
        "height",
    ),
    "narrative": (
        "atmosphere",
        "story",
        "theme",
        "mood",
        "feel",
        "old-school",
        "dated",
    ),
}

NEG = (
    "not fun",
    "ugly",
    "boring",
    "buggy",
    "unfinished",
    "lost",
    "killed",
    "confusing",
    "not enough",
    "sickens",
    "tormented",
    "no-go",
    "no exit",
    "error",
)
POS = ("good", "great", "fun", "favorite", "atmosphere", "nice", "improves")
PLAYABILITY = (
    "lost",
    "bug",
    "softlock",
    "no exit",
    "killed",
    "error",
    "unfinished",
    "not enough weapon",
)


def tag_pillars(text: str) -> dict[str, float]:
    blob = text.lower()
    hits: dict[str, float] = {}
    for pillar, terms in PILLAR_TERMS.items():
        n = sum(1 for t in terms if t in blob)
        if n:
            hits[pillar] = min(1.0, 0.35 * n)
    return hits


def _polarity(text: str) -> float:
    blob = text.lower()
    score = 0.0
    for w in sorted(NEG, key=len, reverse=True):
        if w in blob:
            score -= 1.0
            blob = blob.replace(w, " ")
    for w in sorted(POS, key=len, reverse=True):
        if w in blob:
            score += 1.0
            blob = blob.replace(w, " ")
    return score


def _severity(text: str) -> str:
    blob = text.lower()
    play = any(w in blob for w in PLAYABILITY)
    style = any(w in blob for w in ("ugly", "texture", "atmosphere", "look", "detail"))
    if play and style:
        return "mixed"
    if play:
        return "playability"
    if style:
        return "style"
    return "mixed"


def _lesson(review: Review, polarity: float) -> str:
    first = review.text.split(".")[0].strip()
    if len(first) > 160:
        first = first[:157] + "…"
    if polarity < 0:
        return f"Avoid: {first}."
    if polarity > 0:
        return f"Keep: {first}."
    return f"Note: {first}."


def critic_target(review: Review, file_rec: FileRecord | None = None) -> dict[str, Any]:
    weights = tag_pillars(review.text)
    polarity = _polarity(review.text)
    vote = review.vote
    if vote is None:
        if polarity > 0:
            vote = 4
        elif polarity < 0:
            vote = 2
        else:
            vote = 3
    pillars: dict[str, Any] = {}
    for name in PILLAR_TERMS:
        if name not in weights:
            pillars[name] = {"score": None, "notes": ""}
            continue
        # Pull the vote toward 3 when the mention is weak.
        score = round((vote * 0.7 + 3.0 * 0.3), 2)
        if polarity < 0:
            score = min(score, float(vote))
        pillars[name] = {
            "score": max(0.0, min(5.0, score)),
            "notes": review.text[:180],
        }
    title = file_rec.title if file_rec else ""
    return {
        "title": title,
        "pillars": pillars,
        "lessons": [_lesson(review, polarity)],
        "severity": _severity(review.text),
        "keep": True,
        "vote": vote,
    }


def records_from_file(file_rec: FileRecord) -> list[ChatRecord]:
    rows: list[ChatRecord] = []
    stem = (file_rec.filename or file_rec.title or "file").replace(".zip", "")
    for i, rev in enumerate(file_rec.reviews):
        target = critic_target(rev, file_rec)
        user = (
            f"idgames file: {file_rec.title} ({file_rec.filename})\n"
            f"author: {file_rec.author}\n"
            f"description: {file_rec.description}\n"
            f"player comment ({rev.username}, vote={rev.vote}): {rev.text}\n"
            "Map this comment onto the five design pillars. JSON only."
        )
        rows.append(
            ChatRecord(
                id=f"community:{stem}:critic:{i}",
                source="community",
                task=CRITIC_TASK,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": dumps_json(target)},
                ],
                meta={
                    "idgames_id": file_rec.id,
                    "filename": file_rec.filename,
                    "severity": target["severity"],
                    "lessons": target["lessons"],
                },
            )
        )
    if file_rec.description and not file_rec.reviews:
        # Listing-only: teach brief extraction from archive metadata.
        brief = {
            "theme": file_rec.title,
            "brief": file_rec.description,
            "source": "idgames",
            "constraints": ["axis-aligned DoomLayoutV0", "free textures only"],
        }
        rows.append(
            ChatRecord(
                id=f"community:{stem}:brief",
                source="community",
                task="brief",
                messages=[
                    {
                        "role": "system",
                        "content": "Write a compact DoomLayoutV0 brief from idgames metadata. JSON only.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Title: {file_rec.title}\nAuthor: {file_rec.author}\n"
                            f"Description: {file_rec.description}\nJSON only."
                        ),
                    },
                    {"role": "assistant", "content": dumps_json(brief)},
                ],
                meta={"idgames_id": file_rec.id, "filename": file_rec.filename},
            )
        )
    return rows


def lessons_from_records(records: list[ChatRecord], *, k: int = 24) -> list[str]:
    seen: list[str] = []
    have: set[str] = set()
    for rec in records:
        for lesson in rec.meta.get("lessons") or []:
            if lesson not in have:
                have.add(lesson)
                seen.append(lesson)
            if len(seen) >= k:
                return seen
    return seen
