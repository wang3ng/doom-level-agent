"""Stage 2: text (+ optional image path) -> layout JSON via Ollama."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

DEFAULT_API = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("LAYOUT_MODEL", "qwen3-coder:30b")

SYSTEM = """You are a Doom level layout planner.
Output ONLY valid JSON matching this shape:
{
  "name": "string",
  "theme": "string",
  "brief": "string",
  "rooms": [{"id":"r1","x":0,"y":0,"w":256,"h":256,"floor_height":0,"ceiling_height":128,"light":160}],
  "connections": [{"a":"r1","b":"r2","kind":"corridor","width":64}],
  "things": [{"type":"Player1Start","x":128,"y":128,"angle":0}]
}
Rules:
- Axis-aligned rooms only; sizes multiples of 64; coordinates integers.
- Exactly one Player1Start inside some room.
- Connections must reference existing room ids; graph should be connected.
- Use free Doom texture names only when setting flats (FLOOR0_1, CEIL1_1, etc.).
- No markdown fences.
"""


def _chat(prompt: str, model: str = DEFAULT_MODEL, api_base: str = DEFAULT_API) -> str:
    url = api_base.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["message"]["content"]


def brief_to_layout(
    brief: str,
    *,
    image_hint: str | None = None,
    model: str = DEFAULT_MODEL,
    api_base: str = DEFAULT_API,
) -> dict[str, Any]:
    user = f"Design a small playable Doom layout for this brief:\n{brief}\n"
    if image_hint:
        user += f"\nConcept image notes / path: {image_hint}\n"
    user += "Return JSON only."
    raw = _chat(user, model=model, api_base=api_base)
    return json.loads(raw)
