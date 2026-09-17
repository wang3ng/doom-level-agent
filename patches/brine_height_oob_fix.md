# brine UDMF height/OOB local patch (NOT committed/pushed)

## Files changed
- `src/udmf/writer.py` (local only)
- rebuilt `data/maps/brine_pump_station.wad` + `.txt`

## Fixes applied

### 1) `_apply_door_linedefs` — keep STEP lowers on height-mismatched doors
Previously always blanked `texturebottom` on the door-side sidedef. That wiped the
STEP2/STEPTOP riser when adjacent floors differ (hub 0 vs arena 16 on yellow lock),
producing HOM/black void on the step face once the door opens.

### 2) `_emit_cover_props` — solid one-sided pillars / tall cover
`pillar` and `cover_block` with `floor_raise > 24` now emit **one-sided** blocking
linedefs (CCW, midtex faces into parent room) instead of two-sided raised platforms.
Removes edge-snag on impassable height deltas and avoids walkable "pillar tops".
Short pedestals (`floor_raise <= 24`, e.g. yellow key) stay two-sided raised platforms.

### 3) Comment in `_door_fields`
Documents that door pads sit at `lo` and depend on preserved step textures.

## Smoke
GZDoom g4.14.2 + freedoom2.wad loaded MAP01, echoed SMOKE_BRINE_OK, exit 0.
No UDMF parse errors. Interactive void/hotspot re-verify still needed in-game.
