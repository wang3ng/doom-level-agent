"""VLM critic stub — pull qwen2.5-vl (or similar) on william when VRAM allows."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def critique_screenshots(
    screenshot_paths: list[Path],
    brief: str,
) -> dict[str, Any]:
    return {
        "status": "stub",
        "brief": brief,
        "n_shots": len(screenshot_paths),
        "scores": {
            "style_alignment": None,
            "readability": None,
            "combat_clarity": None,
        },
        "notes": "Wire local VLM via Ollama multimodal chat when available.",
    }
