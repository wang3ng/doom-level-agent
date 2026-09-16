"""Shared micro-design guidance for strong describers and layout planners."""

from __future__ import annotations

PART_DESIGN_RULES = """
Micro-design (required — be NUMERIC and NAMED, not vague):
- Every room: shape WITH aspect (e.g. 320x160 wide, 96x256 narrow shaft, L with wing_side/wing_w/wing_h).
- Textures: name Doom wall + floor + ceiling (STARTAN3 vs BROWN96 vs SLADWALL vs GSTONE1 vs COMPSPAN). Never leave all rooms on STARTAN2.
- Light: integer 0-255 per room plus optional light_special (17 flicker, 1 blink, 8 glow). Enforce hierarchy (start>=220, maze<=80, key>=200, hazard~96, exit~200).
- Elevation: exact floor/ceiling ints; uneven links use kind=lift (plat elevator) or STEP risers — never a silent permanent drop without STEP/lift.
- Cover: typed props (cover_block/pillar) with sizes; pillars use METAL, blocks SUPPORT3.
- Triggers: lock color, walk closet, lift, exit — named explicitly.
- Anti-pattern: identical rectangles, identical walls, flat light~160 everywhere, fake 'elevator' that is only a floor delta.
""".strip()

PART_DESIGN_JSON_HINT = """
"part_designs": [
  {
    "id": "service_choke",
    "role": "choke",
    "shape": "narrow dogleg hallway",
    "elevation": "ceiling 16 lower than hub for pressure; STEP risers if floors differ",
    "cover": "one 32x32 mid-hall cover_block for peek shooting",
    "mobs": "none",
    "triggers": "none",
    "light": "dim vs bright start",
    "textures": "tech / darker flats",
    "detail": "Darker light, breadcrumb clip, forces single-file approach into hub."
  }
]
""".strip()


def classic_guidance_for(theme_or_brief: str, *, k: int = 2) -> str:
    """Primer + matched classic map refs for prompting."""
    try:
        from corpus.classic import format_classic_block

        return format_classic_block(theme_or_brief, k=k, include_primer=True, max_parts=10)
    except Exception:
        return PART_DESIGN_RULES
