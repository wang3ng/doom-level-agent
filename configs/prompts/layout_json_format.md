# Layout JSON format (DoomLayoutV0) — for JSON→WAD agents

The LLM fills **layout JSON** only. `src/udmf/writer.py` compiles it to UDMF/PWAD.
Schema: `configs/schema/layout.schema.json`. Validate with `pipeline.validate.validate_layout`.
After build, run `python scripts/hull_audit.py` before claiming a map is playable.

---

## Top-level object

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Map id / stem (e.g. `brine_pump_station`) |
| `theme` | no | Style tag (`techbase`, `nukage`, …) |
| `brief` | no | 3–6 concrete sentences (start → hub → key → peak → exit) |
| `objective_room` | strongly yes | Room id that holds `ExitSwitch` |
| `part_designs` | strongly yes | One micro-spec per major space (prose; see below) |
| `rooms` | yes | Axis-aligned rectangles (or `shape:"L"` with wing) |
| `connections` | yes | Edges between room ids; writer inserts corridor/door/lift sectors |
| `props` | optional | Cover pillars/blocks inside rooms |
| `closets` | optional | Monster closets attached to a room side |
| `things` | yes | Player start, monsters, items, keys, `ExitSwitch` |

Coordinates are Doom map units (integers). Prefer multiples of **64** for room `w`/`h`.
**Rooms must not overlap** — leave a gap so a corridor can be inserted.

---

## `rooms[]` — geometry the compiler emits

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable; referenced by connections / props / closets / objective |
| `x`,`y` | int | Southwest corner |
| `w`,`h` | int ≥64 | Main rectangle size |
| `floor_height`,`ceiling_height` | int | Default 0 / 128. Ceiling must be > floor |
| `floor_flat`,`ceil_flat` | string | Free Doom flats (`FLOOR0_1`, `NUKAGE1`, `CEIL1_1`, …) |
| `wall_texture` | string | Free Doom wall (`STARTAN3`, `BROWN96`, `SLADWALL`, `GSTONE1`, `COMPSPAN`, …). **Vary by room** |
| `light` | 0–255 | Hierarchy: start ≥220, hub ~160, maze ≤80, key ≥200, hazard ~96, exit ~200 |
| `light_special` | int | Optional sector special (17 flicker, 1 blink, 8 glow) |
| `role` | string | start / teach / choke / hub / key / hazard / arena / optional / exit |
| `shape` | enum | `rect`/`narrow`/`wide`/`alcove`/`arena`/`hub`/`dogleg` or **`L`** |
| `wing_side`,`wing_w`,`wing_h` | | **Required when `shape` is `L`**. Wing is a true 6-vertex polygon, not a second room |
| `design` | string | Short note |

### L-rooms (critical)

- One room object with `"shape":"L"` + `wing_side` + `wing_w` + `wing_h`.
- Do **not** invent a separate `*_wing` room joined by `kind:"open"` — that becomes two boxes, not an L.
- Connections attach only to the **real outline face**. An east wing’s right face exists only for `y ∈ [room.y, room.y+wing_h]`, not the full AABB height. Keep door/lift width **well inside** that span (leave ≥32–48u wall on each side of a short wing face).

---

## `connections[]` — how rooms join

| Field | Notes |
| --- | --- |
| `a`,`b` | Existing room ids |
| `kind` | `corridor` (open passage), `door` (raise door), `open` (same), **`lift`** (walk-on plat elevator) |
| `lock` | `blue` / `yellow` / `red` — use with `kind:"door"`; place matching `*Card` off the locked path |
| `width` | Opening width ≥32 (64 typical; 96 for landmark doors) |
| `design` | Short note |

**Elevation rules**

- Same floor heights → `corridor` / `door` / `open`.
- Floor delta ≤24 → STEP risers on the portal (compiler draws STEP2/STEPTOP). Still use a gap between rooms.
- Floor delta >24 that should be rideable → **`kind:"lift"`** (starts flush with higher floor, lowers to lower neighbor). Never fake an elevator with only a silent floor drop.
- Locked doors across unequal floors are OK; the compiler keeps STEP bottoms (do not assume midtex alone blocks).

---

## `props[]` — cover / pillars

| Field | Notes |
| --- | --- |
| `type` | `cover_block` or `pillar` |
| `x`,`y`,`w`,`h` | Axis-aligned footprint **fully inside** `in_room` |
| `floor_raise` | Pedestal ≤**24** (walk-up). Cover/pillar **>24** = solid blocker |
| `in_room` | Parent room id |
| `design` | What it does for the player |

**Placement (playtest-hardened)**

- Keep a clear walk lane ≥64u from spawn → first door and along corridor midlines.
- Never put cover on the **centerline** of a choke/corridor the player must cross.
- Pillars are landmarks — offset from portal mouths by ≥48u.
- Closet / exit / other rooms must not overlap prop AABBs or each other.

---

## `closets[]`

| Field | Notes |
| --- | --- |
| `id`,`attach_room`,`side` | Parent room + compass side |
| `w`,`h`,`gap` | Closet size and corridor gap to parent |
| `trigger` | `walk` (tripwire opens door) or `use` |
| `monsters` | `{type, dx, dy, angle}` relative to closet origin |
| floors/ceil/light | Match parent combat area when possible |

Place closets so their AABB does **not** collide with other rooms (e.g. exit bay past the closet).

---

## `things[]`

Allowed types: `Player1Start`, `Zombieman`, `ShotgunGuy`, `Imp`, `HealthBonus`, `Clip`, `Shotgun`, `ArmorBonus`, `BlueCard`, `YellowCard`, `RedCard`, `ExitSwitch`.

- Exactly one `Player1Start` inside a room (not inside a prop).
- Exactly one `ExitSwitch` inside `objective_room` near a far wall.
- Keys go in key rooms / alcoves — **not** in the same room as their locked door with no return.

---

## `part_designs[]` — prose micro-specs (description format)

These are **authoring notes** the geometry agent must honor. Every room on the solution path needs one entry. Fields are strings; write **measurable** content, not mood adjectives.

| Field | Good example | Bad example |
| --- | --- | --- |
| `id` | `plant_hub` | `room2` |
| `role` | `hub` | `cool area` |
| `shape` | `L: main 384x288 + east wing 160x160 (wing_side=east)` | `interesting shape` |
| `elevation` | `floor 0 / ceil 176; lift south to shotgun at -24` | `some stairs` |
| `cover` | `64x64 METAL pillar at ~center, ≥48u from portals` | `crates somewhere` |
| `mobs` | `1 zombieman east of cover; no hub fight` | `enemies` |
| `triggers` | `kind=lift to shotgun; yellow door south; walk closet east on arena` | `locked stuff` |
| `light` | `160 mid; start 255; maze 64+special 17` | `atmospheric` |
| `textures` | `walls BROWN96; floor FLOOR1_1; ceil CEIL1_2` | `tech look` |
| `detail` | `Sightline bends at L; pillar is landmark AND cover` | `feels epic` |

Also fill free-text `design` on rooms/connections/props with the same specificity when useful.

---

## Known playtest failure modes (JSON→WAD) — avoid these

Compiled from brine / nuclear GZDoom+Freedoom playtests. Details in `patches/`.

1. **Prop on the critical walk lane** — tall `cover_block`/`pillar` in the spawn→door or corridor midline. Player hits an invisible solid; past it the next room floor is visible → feels like a barrier/OOB. **Fix in JSON:** offset cover (≥32–48u off lane).
2. **Hollow / snaggy props** — writer now self-refs solids; still: don’t stack props on portals; keep pedestals `floor_raise≤24`.
3. **L-room as two boxes** — separate wing room + open joint. Looks rectilinear; portals use wrong faces. **Use single `shape:"L"`**.
4. **Half-door / portal punch** — door width flush with a short L-wing face (AABB mid vs real wing span). Screenshot: half BIGDOOR / half wall. **Center openings inside the real wing span with margins.**
5. **Fake elevator** — only `floor_height` delta, `kind` not `lift`. Player drops permanently or can’t return. **Use `kind:"lift"`** for rideable pads.
6. **Height-mismatched door without STEP read** — writer keeps STEP bottoms; still set honest floor ints and prefer ≤24 step or a lift.
7. **Closet overlaps exit/other room** — automap dissolves / void at map edge. **Gap closets from neighbors.**
8. **Missing key loop** — key in locked room or no hub return. Prefer hub: key wing → return → locked arena/exit.
9. **Identical STARTAN2 + light 160 everywhere** — affordance pillar dies; scorer punishes. Name walls/lights per room.
10. **ExitSwitch missing / wrong room** — map not finishable. Place in `objective_room`.

**Before shipping a WAD:** `stage3_build` runs `pipeline.hull_gate` automatically and **refuses to write** on failure. Manually: `python scripts/hull_audit.py`. Then fair-play the critical path (no noclip).

Hull gate checks include: room/closet overlaps, PROP_VOID, PROP_ON_PORTAL_MIDLINE, corridor clearance ≥32, portal punch (doors **and** lifts), HALF_PORTAL_APPEARANCE, and r=16 walkability BFS from spawn to ExitSwitch.
