#!/usr/bin/env python3
"""Ask Ollama for a short Doom level design brief."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "briefs" / "agent_generated.txt"
API = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3-coder:30b"

BODY = {
    "model": MODEL,
    "stream": False,
    "messages": [
        {
            "role": "system",
            "content": (
                "You write concise Doom level design briefs. "
                "Output 2-4 sentences only. No markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate one short original Doom (GZDoom) level description "
                "suitable as a design brief for an automated UDMF builder. "
                "Theme: techbase. Keep geometry simple (few rooms). "
                "Mention combat tone and one landmark."
            ),
        },
    ],
    "options": {"temperature": 0.7, "num_predict": 180},
}


def main() -> None:
    req = urllib.request.Request(
        API,
        data=json.dumps(BODY).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["message"]["content"].strip()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"--- saved {OUT} ---")


if __name__ == "__main__":
    main()
