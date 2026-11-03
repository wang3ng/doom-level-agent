"""idgames frontend/API ingest. Never stores emails or full TEXTFILEs.

The JSON API (doomworld.com/idgames/api) is the preferred live source but is
often behind Cloudflare. The HTML/markdown frontend parser is the fallback,
and committed fixtures keep the pack reproducible offline.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

DEFAULT_API = "https://www.doomworld.com/idgames/api/api.php"
DEFAULT_FRONT = "https://www.doomworld.com/idgames/"
USER_AGENT = (
    "doom-level-agent/0.1 (+https://github.com/wang3ng/doom-level-agent; "
    "course research scraper; 1 req/s)"
)
MAX_DESC = 600
MAX_REVIEW = 400
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
IDGAMES_ID_RE = re.compile(r"idgames://(\d+)")
VOTE_RE = re.compile(r"\b([1-5])\s*/\s*5\b")
VOTES_RE = re.compile(r"\((\d+)\s+votes?\)", re.I)
MD_CELL_RE = re.compile(
    r"\|\s*([A-Za-z][^|]{0,40}?):\s*\|\s*(.*?)\s*\|",
)
HTML_CELL_RE = re.compile(
    r"(Title|Filename|Author|Description|Rating|E-?mail):\s*</t[dh]>\s*"
    r"<t[dh][^>]*>(.*?)</t[dh]>",
    re.I | re.S,
)
MD_REVIEW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*)\|?\s*$",
    re.M,
)

SEED_PAGES = [
    "levels/doom2/s-u/trouble",
    "levels/doom2/d-f/dickie02",
    "levels/doom2/Ports/d-f/derceto",
    "levels/doom2/Ports/megawads/gd",
]


class IdgamesBlocked(RuntimeError):
    """Cloudflare or similar interstitial instead of API/HTML payload."""


@dataclass
class Review:
    username: str
    text: str
    vote: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileRecord:
    title: str
    filename: str
    author: str = ""
    description: str = ""
    dir: str = ""
    id: int | None = None
    votes: int | None = None
    rating: float | None = None
    url: str = ""
    reviews: list[Review] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def scrub(text: str | None) -> str:
    if not text:
        return ""
    return EMAIL_RE.sub("[redacted]", str(text)).strip()


def truncate(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def sanitize_file(rec: FileRecord) -> FileRecord:
    rec.title = truncate(scrub(rec.title), 120)
    rec.author = truncate(scrub(rec.author), 80)
    rec.description = truncate(scrub(rec.description), MAX_DESC)
    rec.filename = scrub(rec.filename)
    cleaned: list[Review] = []
    for rev in rec.reviews:
        text = truncate(scrub(rev.text), MAX_REVIEW)
        user = truncate(scrub(rev.username) or "Anonymous", 40)
        if not text or set(text) <= set("-: "):
            continue
        vote = rev.vote
        if vote is None:
            m = VOTE_RE.search(text)
            vote = int(m.group(1)) if m else None
        cleaned.append(Review(username=user, text=text, vote=vote))
    rec.reviews = cleaned
    return rec


def _looks_blocked(payload: str) -> bool:
    head = payload[:800].lower()
    return "just a moment" in head or "cf-browser-verification" in head


def _split_filename(path: str) -> tuple[str, str]:
    path = path.strip()
    if "/" not in path:
        return "", path
    dir_, name = path.rsplit("/", 1)
    if not dir_.endswith("/"):
        dir_ += "/"
    return dir_, name


def parse_idgames_page(text: str, *, url: str = "") -> FileRecord:
    """Parse idgames frontend HTML *or* markdown tables into a FileRecord."""
    if _looks_blocked(text):
        raise IdgamesBlocked("idgames frontend returned a bot interstitial")

    meta: dict[str, str] = {}
    for key, val in MD_CELL_RE.findall(text):
        meta[key.strip().lower()] = val.strip()
    if "title" not in meta:
        for key, val in HTML_CELL_RE.findall(text):
            clean = re.sub(r"<[^>]+>", " ", val)
            meta[key.strip().lower()] = re.sub(r"\s+", " ", clean).strip()

    filename = meta.get("filename", "")
    directory, fname = _split_filename(filename)
    title = meta.get("title") or (fname.replace(".zip", "") if fname else "untitled")
    rating_raw = meta.get("rating", "")
    votes = None
    vm = VOTES_RE.search(rating_raw)
    if vm:
        votes = int(vm.group(1))

    file_id = None
    im = IDGAMES_ID_RE.search(text)
    if im:
        file_id = int(im.group(1))

    reviews: list[Review] = []
    chunk = text
    parts = re.split(r"Reviews\s*:", text, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        chunk = re.split(r"View\s+\S+\.txt", parts[1], maxsplit=1)[0]
        chunk = re.split(r"This page was created", chunk, maxsplit=1)[0]
    skip_users = {"username", "reviewer", "reviews", "user"}
    for user, body, _tail in MD_REVIEW_RE.findall(chunk):
        user, body = user.strip(), body.strip()
        if set(user) <= set("-: ") or set(body) <= set("-: "):
            continue
        if "---" in user or "---" in body:
            continue
        if user.lower() in skip_users or not body:
            continue
        if user.lower().endswith(":") or body.lower() in {"x"}:
            continue
        reviews.append(Review(username=user, text=body))

    rec = FileRecord(
        title=title,
        filename=fname or filename,
        author=meta.get("author", ""),
        description=meta.get("description", ""),
        dir=directory,
        id=file_id,
        votes=votes,
        url=url,
        reviews=reviews,
    )
    return sanitize_file(rec)


def parse_api_get(payload: dict[str, Any], *, url: str = "") -> FileRecord:
    content = payload.get("content") or payload
    reviews_block = content.get("reviews") or {}
    raw_reviews = reviews_block.get("review") if isinstance(reviews_block, dict) else reviews_block
    if raw_reviews is None:
        raw_reviews = []
    if isinstance(raw_reviews, dict):
        raw_reviews = [raw_reviews]
    reviews = []
    for item in raw_reviews:
        if not isinstance(item, dict):
            continue
        vote = item.get("vote")
        try:
            vote_i = int(vote) if vote not in (None, "") else None
        except (TypeError, ValueError):
            vote_i = None
        reviews.append(
            Review(
                username=str(item.get("username") or "Anonymous"),
                text=str(item.get("text") or ""),
                vote=vote_i,
            )
        )
    filename = str(content.get("filename") or "")
    directory = str(content.get("dir") or "")
    rec = FileRecord(
        title=str(content.get("title") or filename),
        filename=filename,
        author=str(content.get("author") or ""),
        description=str(content.get("description") or ""),
        dir=directory,
        id=int(content["id"]) if content.get("id") not in (None, "") else None,
        votes=int(content["votes"]) if content.get("votes") not in (None, "") else None,
        rating=float(content["rating"]) if content.get("rating") not in (None, "") else None,
        url=url or str(content.get("url") or ""),
        reviews=reviews,
    )
    return sanitize_file(rec)


def _http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429, 503):
            raise IdgamesBlocked(f"HTTP {exc.code}: {url}") from exc
        raise
    text = raw.decode("utf-8", errors="replace")
    if _looks_blocked(text):
        raise IdgamesBlocked(f"blocked: {url}")
    return text


def fetch_api_get(
    *,
    file_id: int | None = None,
    file_path: str | None = None,
    api_base: str = DEFAULT_API,
    opener: Callable[[str], str] | None = None,
) -> FileRecord:
    get = opener or _http_get
    q = f"{api_base}?action=get&out=json"
    if file_id is not None:
        q += f"&id={int(file_id)}"
    elif file_path:
        q += f"&file={urllib.parse.quote(file_path)}"
    else:
        raise ValueError("file_id or file_path required")
    body = get(q)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise IdgamesBlocked(f"non-JSON API response for {q}") from exc
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return parse_api_get(payload, url=q)


def fetch_frontend_page(
    page: str,
    *,
    front_base: str = DEFAULT_FRONT,
    opener: Callable[[str], str] | None = None,
) -> FileRecord:
    get = opener or _http_get
    url = front_base.rstrip("/") + "/" + page.lstrip("/")
    text = get(url)
    return parse_idgames_page(text, url=url)


def load_fixture_files(fixtures_dir: Path) -> list[FileRecord]:
    records = []
    for path in sorted(fixtures_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        reviews = [
            Review(
                username=r.get("username", "Anonymous"),
                text=r.get("text", ""),
                vote=r.get("vote"),
            )
            for r in data.get("reviews") or []
        ]
        rec = FileRecord(
            title=data.get("title", path.stem),
            filename=data.get("filename", ""),
            author=data.get("author", ""),
            description=data.get("description", ""),
            dir=data.get("dir", ""),
            id=data.get("id"),
            votes=data.get("votes"),
            rating=data.get("rating"),
            url=data.get("url", ""),
            reviews=reviews,
        )
        records.append(sanitize_file(rec))
    pages = fixtures_dir / "pages"
    if pages.is_dir():
        for path in sorted(pages.glob("*.md")):
            # Parser tests / extra harvests; skip if a JSON fixture already covers the stem.
            if (fixtures_dir / f"{path.stem}.json").is_file():
                continue
            records.append(
                parse_idgames_page(path.read_text(encoding="utf-8"), url=str(path))
            )
    return records


def scrape_pages(
    pages: list[str] | None = None,
    *,
    delay_s: float = 1.2,
    opener: Callable[[str], str] | None = None,
) -> list[FileRecord]:
    pages = pages or SEED_PAGES
    out: list[FileRecord] = []
    for i, page in enumerate(pages):
        if i and opener is None:
            time.sleep(delay_s)
        out.append(fetch_frontend_page(page, opener=opener))
    return out
