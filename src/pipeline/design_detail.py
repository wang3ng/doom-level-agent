"""Shared micro-design guidance for strong describers and layout planners."""

from __future__ import annotations

from pathlib import Path

_PROMPTS = Path(__file__).resolve().parents[2] / "configs" / "prompts"
_FORMAT_PATH = _PROMPTS / "layout_json_format.md"


def load_layout_json_format() -> str:
    """Full DoomLayoutV0 field guide + playtest hazards for JSON→WAD agents."""
    try:
        return _FORMAT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return PART_DESIGN_RULES + "\n\n" + WRITER_PLAYTEST_HAZARDS


PART_DESIGN_RULES = """
Micro-design (required — be NUMERIC and NAMED, not vague):
- Critical path first: start → teach → hub/key → peak → calm exit must stay physically walkable (player radius 16). Pretty rooms are secondary.
- Every room: shape WITH aspect (e.g. 320x160 wide, 96x256 narrow shaft, L with wing_side/wing_w/wing_h).
- L-rooms: ONE room with shape "L" + wing_side/wing_w/wing_h — never a second *_wing room.
- Textures: name Doom wall + floor + ceiling (STARTAN3 vs BROWN96 vs SLADWALL vs GSTONE1 vs COMPSPAN). Never leave all rooms on STARTAN2.
- Light hierarchy: start>=220, dim choke, hub~160 with landmark, key>=200, hazard~96, exit~200. Optional light_special (17 flicker, 1 blink, 8 glow).
- Elevation: exact floor/ceiling ints; uneven links use kind=lift or STEP risers (<=24) — never a silent permanent drop.
- Cover: typed props with sizes. Hub landmark / pillars OFFSET >=64-96u from ALL portal midlines. Never on spawn→door or corridor centerline.
- Combat economy: max 1 weak enemy before first weapon pickup; no spawn-under-fire without cover + clear lane. Closets fire mid-fight, not in the doorway face.
- Triggers: lock color, walk closet, lift, exit — named explicitly. Key detour short; return through hub before the gate.
- Anti-pattern: identical rectangles, identical walls, flat light~160, fake elevator, door flush on short L-wing face, closet overlapping exit, prop on approach axis.
""".strip()

WRITER_PLAYTEST_HAZARDS = """
JSON→WAD playtest hazards (do NOT emit layouts that cause these):
1) Prop on critical walk lane or portal midline/approach (spawn→door, corridor center) → invisible solid / false OOB. Landmark pillars >=64-96u from portal mids.
2) Separate wing room instead of shape "L" → boxy fake-L; portal faces wrong.
3) Door/lift width flush on short L-wing face → half BIGDOOR / half wall (portal punch). Lifts need the same full punch as doors.
4) Floor delta without kind "lift" when player must ride back → fake elevator / softlock.
5) Closet AABB overlapping exit or neighbor → void at map edge.
6) Key in locked room or no hub return → unfinished critical path.
7) Pedestal floor_raise >24 when it should be walk-up; tall cover on portal mouth.
8) Missing ExitSwitch in objective_room.
9) Early combat too harsh: >1 weak enemy before shotgun / spawn under fire.
Pipeline refuses WADs that fail scripts/hull_audit.py (overlap, PROP_ON_PORTAL_MIDLINE, portal punch, r=16 walkability BFS spawn→exit).
""".strip()

PART_DESIGN_JSON_HINT = """
"part_designs": [
  {
    "id": "service_choke",
    "role": "choke",
    "shape": "narrow 192x128 east-west hall (aspect ~1.5)",
    "elevation": "floor 0 / ceil 112; same as hub — no silent drop",
    "cover": "32x32 cover_block at (296,144) OFF corridor midline — peek only",
    "mobs": "none",
    "triggers": "open corridor east to hub",
    "light": "140 dim vs start 255",
    "textures": "walls SUPPORT3/STARTAN2; floor FLOOR0_3; ceil FLAT5_4",
    "detail": "Single-file approach; cover is flank not barrier."
  },
  {
    "id": "plant_hub",
    "role": "hub",
    "shape": "L: main 384x288 + east wing 160x160 (wing_side=east)",
    "elevation": "floor 0 / ceil 176; kind=lift south to shotgun_nook floor -24",
    "cover": "64x64 METAL pillar near center, >=48u from all portals",
    "mobs": "none in hub",
    "triggers": "lift south; door east into wing face (opening centered with margins); red/yellow lock south",
    "light": "160",
    "textures": "walls BROWN96; floor FLOOR1_1; ceil CEIL1_2",
    "detail": "True L polygon; east door must sit inside wing y-span with wall margins."
  }
]
""".strip()

LAYOUT_JSON_COMPACT = """
Emit DoomLayoutV0 JSON:
- rooms: id,x,y,w,h,floor_height,ceiling_height,floor_flat,ceil_flat,wall_texture,light[,light_special],role,shape[,wing_side,wing_w,wing_h],design
- connections: a,b,kind(corridor|door|open|lift),width[,lock blue|yellow|red],design — leave geometric GAPS between rooms
- props: type cover_block|pillar, x,y,w,h,floor_raise,in_room,design — clear walk lanes
- closets: id,attach_room,side,w,h,gap,trigger walk|use,monsters[]; no overlap with other rooms
- things: Player1Start; ExitSwitch in objective_room; keys off locked path; monsters/items inside rooms not props
- part_designs: one measurable entry per room (shape/elevation/cover/mobs/triggers/light/textures/detail)
""".strip()


def classic_guidance_for(theme_or_brief: str, *, k: int = 2) -> str:
    """Primer + matched classic map refs for prompting."""
    try:
        from corpus.classic import format_classic_block

        return format_classic_block(theme_or_brief, k=k, include_primer=True, max_parts=10)
    except Exception:
        return PART_DESIGN_RULES
