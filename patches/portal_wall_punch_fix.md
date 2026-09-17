# Portal wall punch — half-door on L-wing faces (local fix, NOT pushed)

## Symptom
Fair-play screenshot `nuclear_04_current_blocker.png`: doorway split vertically —
left BIGDOOR2 (+ hazard in texture), right continuing BROWN96, impassable seam.
Player in plant_hub near nukage/shotgun approach (view matched **east-wing maze door**).

Brine still reported black void despite `hull_audit` 29/29 PASS — reconciled as
prior hollow-prop / camera-clip class of issue (see `deep_hull_audit.md`); this
pass prioritizes proving door/lift openings are fully punched.

## Root cause
`materialize_corridors` placed openings using **AABB** side overlap, not the
**real L-outline** span on the shared face.

`plant_hub` is an east-wing L:
- AABB right face y ∈ [64, 352]
- Real wing right face @ x=928 only y ∈ [64, 224]

`plant_hub ↔ dark_maze` door (width 64) centered on AABB overlap mid=192 →
corridor y ∈ [160, 224] — **flush with the wing top**. On the 160-mu wing face
that reads as half BIGDOOR / half BROWN96 (wall [64,160] + door [160,224]).

TEXTMAP before fix (east wing x=928):
```
[64,160]  WALL BROWN96
[160,224] OPEN BIGDOOR2  (flush_high)
```

Hub south portals (lift / red door / start corridor) were already fully punched;
the half-door was the maze door on the wing, not a residual coplanar wall on the
same portal span.

## Fix
`src/udmf/writer.py`:
1. `_side_span_at(room, side, const)` — real outline span on an AABB face
2. `_place_opening(overlap, width)` — center width inside that span
3. `materialize_corridors` joins on real-face ∩ real-face, not AABB∩AABB
4. `_openings_for_room` clips punches to the real span (defensive)

After fix (east wing x=928):
```
[64,112]  WALL
[112,176] OPEN BIGDOOR2  (48mu margins both sides)
[176,224] WALL
```

## Audit extension
`scripts/hull_audit.py` now also flags:
- `PORTAL_WALL_OVERLAP` — coplanar one-sided wall overlapping a portal XY span
- `PORTAL_INCOMPLETE_PUNCH` — twosided cover < corridor gap
- `DOOR_SIBLING_WALL` — one-sided still blocking a door/lift portal span
- `PORTAL_PAST_EDGE` — corridor past real L-face
- `HALF_PORTAL_APPEARANCE` — flush opening ~30–70% of a short L face

Old flush maze door → `HALF_PORTAL_APPEARANCE` (proven with old-sim bounds).
Post-fix: brine + nuclear **PASS (0 issues)**.

## Rebuild (local)
- `data/maps/nuclear_plant_v0.wad` + `.txt`
- `data/maps/brine_pump_station.wad` + `.txt` (unchanged geometry; rebuilt)

Smoke: `SMOKE_nuclear_plant_v0_OK`, `SMOKE_brine_pump_station_OK`

## Hub openings diagram (post-fix)
```
                    top y=352
         +----------[red_key 64]----------+
         |              544-608            |
 left    |            plant_hub            | inner right x=768
 x=384   |                                 +----[wing top y=224]----+
 200-280 |                                 |   maze door 112-176    | x=928
 [start] |                                 |   (centered, 48/48)    |
         +----[lift 64]--|--[red door 96]--+------------------------+
         464-528           544-640              bottom y=64
```
