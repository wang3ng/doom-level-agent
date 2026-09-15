"""Stage 1 stub: concept image generation (local diffusion / ComfyUI later)."""

from __future__ import annotations

from pathlib import Path


def generate_concept_image(brief: str, out_path: Path) -> Path:
    """Placeholder until SDXL/Flux is wired on william.

    Writes a tiny SVG moodboard so the pipeline has an artifact path.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    safe = brief.replace("<", "").replace(">", "")[:200]
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a1510"/>
      <stop offset="100%" stop-color="#5a3a28"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#g)"/>
  <text x="24" y="40" fill="#e8dcc8" font-size="16" font-family="serif">concept stub</text>
  <text x="24" y="80" fill="#c4b49a" font-size="12" font-family="monospace">{safe}</text>
</svg>
"""
    if out_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        svg_path = out_path.with_suffix(".svg")
    else:
        svg_path = out_path
    svg_path.write_text(svg, encoding="utf-8")
    return svg_path
