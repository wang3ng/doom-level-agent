# nuclear start_hall → plant_hub barrier (local fix, NOT pushed)

## Symptom
Player could not cross the blue FLOOR1_1 threshold from start_hall into plant_hub.
Noclip into the blocking volume dropped into OOB void.

## Root cause (two cooperating issues)

### 1) Layout: cover_block parked in the spawn lane
`start_hall` cover at **(120, 200)** with `floor_raise=32` occupies y∈[200,232].
Player1Start is at **(64, 240)** (radius 16 → body y∈[224,256]).
Holding forward walks straight into the solid cover. The hub's blue floor stays
visible past/around the block, so it reads as an "invisible wall at the blue
threshold." Noclip into the **one-sided solid prop interior** is true void.

Evidence (playtest bisect on this box):
- no props → walk reaches hub (PASS)
- cover alone at (120,200) → FAIL
- cover moved to (120,168) / (120,280) / (40,180) → PASS
- pillar alone → PASS

### 2) Writer: solid tall props + colinear portal edges
Tall cover/pillars emit one-sided solids (see `brine_height_oob_fix.md`).
A 1-mu inset was added so prop edges are not colinear with room/corridor walls
that share a portal corner coordinate (defensive; layout move is the real fix).

## Files changed (local only)
- `src/udmf/writer.py` — 1-mu inset on prop AABB before solid/platform emit
- `data/layouts/nuclear_plant_v0.json` — start cover `(120,200)` → `(120,168)`
- rebuilt `data/maps/nuclear_plant_v0.wad` + `.txt`
- rebuilt `data/maps/brine_pump_station.wad` + `.txt`

## Smoke
GZDoom g4.14.2 + freedoom2.wad:
- nuclear: walked start→hub onto FLOOR1_1 (PASS); `SMOKE_nuclear_plant_v0_OK`
- brine: `SMOKE_brine_pump_station_OK`
