# Deep hull audit — brine_pump_station + nuclear_plant_v0

Local-only investigation (NOT pushed). Geometry proof preferred over mouse play.

## Symptom (re-verify after prior patches)

- **brine**: blocked at choke/hub; screenshots show full black void (`brine_02_service_or_blocked.png`).
- **nuclear**: reaches hub, then cover/collision → noclip void (`nuclear_02_hub_noclip_void.png`); automap looked “gappy”.

Prior patches (door STEP bottoms, tall props as one-sided solids, 1-mu inset, nuclear cover move) were **insufficient**.

## Method

1. Read `src/udmf/writer.py` hull path end-to-end (rooms, L-wings, corridors, doors, lifts, props, closets).
2. Parsed rebuilt TEXTMAPs; wrote `scripts/hull_audit.py` (nonzero-winding point-in-sector, skip self-ref edges, player-r=16 corridor clearance, room-poly overlap, portal blocking).
3. Probed critical path: spawn, room centers (offset off solid props), corridor midpoints + portal approaches.
4. GZDoom smoke: `+map MAP01` + echo + quit (no GUI play).

## Root causes (with evidence)

### RC1 — One-sided “solid” props are hollow void (PRIMARY)

Tall `pillar` / `cover_block` (`floor_raise > 24`) were emitted as **one-sided** rectangles with midtex facing the room. The prop **interior is not in any sector**.

- Doom/GZDoom blocks the front of one-sided lines, but **corner-clip / wedge / noclip** into the back drops the player into true OOB → black void.
- Matches nuclear report: “cover/collision then noclip void”.
- Matches brine black-screen after bumping choke cover / hub pillar.
- Probe (pre-fix): room centers sitting inside props (`service_choke` @320,224, `pump_hub` @640,224, `plant_hub` @576,208) reported **VOID**; prop-inside samples were void.

**Not** an unsealed room/corridor hull: after fixing the winding test, all corridors and non-prop room samples were walkable sectors.

### RC2 — Nuclear `exit_bay` ∩ `arena_ambush` room overlap

| Room | Bounds |
|------|--------|
| arena_ambush (closet) | [1152,1248] × [-448,-352] |
| exit_bay | [1184,1312] × [-400,-240] |
| Overlap | 64×48 mu (48/48 poly samples) |

Overlapping playable sectors → BSP/visual holes (void-looking walls, automap “gaps”), especially near arena→exit.

### RC3 — Brine choke cover parked on corridor midline

- Corridor through `service_choke`: y ∈ [192,256] (both portals).
- Cover was at y ∈ [200,232] — **on the lane centerline** (y=224).
- Player/AI walking the critical corridor hits the hollow solid (RC1) immediately.
- Side lanes existed (y 128–200 / 232–320) but midline path is what probes and “hold forward” use.

### Non-issues ruled out

| Hypothesis | Result |
|------------|--------|
| Gaps between room AABB and corridor attachment | All corridors had 2 portals + 2 walls; midpoints in sector |
| L-wing phantom openings (AABB side with no real L edge) | No phantom openings on either map |
| Wrong winding / unclosed outer hull | Outer loops closed; “odd degree” verts were closet **tripwire** endpoints only (floating same-sector walk trigger — benign) |
| Portal linedefs with `blocking=true` | None (diff-sector) |
| Door STEP blanking / height HOM | Already patched earlier; not the remaining void |

### Interactive AI playtest vs geometry

Much of the re-verify void was a **false-positive for “unsealed hull”**: geometry was sealed, but **hollow one-sided props** made collision → void look like OOB hull. Automap “gaps” on nuclear were consistent with **overlapping closet/exit** (RC2), not missing corridor punches.

## Fixes applied (local)

### 1) `src/udmf/writer.py` — self-referencing solid props

Replace one-sided hollows with **self-ref two-sided** linedefs:

- both sidedefs → parent sector
- `blocking = true`
- `texturemiddle` = METAL/SUPPORT3 on both faces
- keep 1-mu AABB inset (colinear portal defense)

Interior is still the parent sector (no void). Noclip through the block stays in-sector.

### 2) `data/layouts/brine_pump_station.json`

- Choke cover `(296,200)` → `(296,144)` (south of corridor band 192–256).

### 3) `data/layouts/nuclear_plant_v0.json`

- `exit_bay.x` `1184` → `1280` (clears closet ending at 1248).
- Shifted exit-bay things: HealthBonus, ExitSwitch (+96 x).

## Automated probe — before / after

### Before (one-sided hollows + overlaps + midline cover)

| Map | Critical-path | Prop interiors | Overlaps | Notes |
|-----|---------------|----------------|----------|-------|
| brine | Room centers in props → VOID; corridors OK | Hollow VOID | none | Midline cover blocks choke lane |
| nuclear | plant_hub center in pillar → VOID; corridors OK | Hollow VOID | exit_bay ∩ arena_ambush | Closet/exit overlap |

Corridor clearance (r=16) was already PASS; the void was prop-hollow / overlap, not missing corridors.

### After (`scripts/hull_audit.py` + rebuild)

| Map | Critical-path | Prop interiors | Overlaps | Corridor clearance |
|-----|---------------|----------------|----------|--------------------|
| brine | **29/29 OK** | solid props → parent sector | NONE | all PASS |
| nuclear | **33/33 OK** | solid props → parent sector | NONE | all PASS |

`scripts/hull_audit.py`: both maps **PASS (0 issues)**.

### GZDoom smoke (ET)

```
SMOKE_DEEP_brine_pump_station_OK
SMOKE_DEEP_nuclear_plant_v0_OK
```

Engine: `/usr/games/gzdoom`, IWAD `/usr/share/games/doom/freedoom2.wad`, no UDMF parse errors.

## Updated WAD paths

- `/workspace/doom-level-agent/data/maps/brine_pump_station.wad` (+ `.txt`)
- `/workspace/doom-level-agent/data/maps/nuclear_plant_v0.wad` (+ `.txt`)

Re-audit: ` /workspace/doom-venv/bin/python scripts/hull_audit.py `

## Files touched (local only)

- `src/udmf/writer.py`
- `data/layouts/brine_pump_station.json`
- `data/layouts/nuclear_plant_v0.json`
- `data/maps/brine_pump_station.wad` / `.txt`
- `data/maps/nuclear_plant_v0.wad` / `.txt`
- `scripts/hull_audit.py` (new)
- `patches/deep_hull_audit.md` (this file)
