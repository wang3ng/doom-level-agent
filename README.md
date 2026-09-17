# Doom Level Agent

Multimodal, tool-grounded **Doom / GZDoom** level design for Johns Hopkins **EN.601.762** *Multimodal Understanding and Generation* (Fall 2026).

Natural-language briefs (and optional concept images) become constrained **layout JSON**, then a deterministic compiler writes **UDMF `TEXTMAP`** into a PWAD that opens in **Ultimate Doom Builder (UDB)** and plays in **GZDoom**. Inference is intended to run locally on workstation **william** (Ollama + RTX 3060 Laptop, 6 GB), using free assets only (e.g. Freedoom).

| | |
| --- | --- |
| **Course** | EN.601.762 · Fall 2026 |
| **Proposal due** | Sep 16 (see [`proposal/proposal.pdf`](proposal/proposal.pdf)) |
| **Mid** | Oct 19 report + presentation |
| **Final** | Dec 9 poster · Dec 15 report |
| **Primary compute** | `william` → `~/projects/doom-level-agent` |
| **Local mirror** | `e:\projects\homeworks\doom-level-agent` (Windows) |

---

## Pipeline

```
brief (+ optional concept image)
        │
        ▼
┌───────────────────┐
│ Stage 1 · Image   │  local diffusion / stub SVG today
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Stage 2 · Layout  │  Ollama LLM/VLM → layout JSON (schema-validated)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Stage 3 · Build   │  JSON → UDMF TEXTMAP → PWAD (.wad)
└─────────┬─────────┘
          ▼
   UDB (edit)  ·  GZDoom (play / screenshots)
          │
          ▼
┌───────────────────┐
│ Critic / Scorer   │  design rubric (5 pillars) + density metrics · VLM stub
└───────────────────┘
```

**Design rule:** the LLM does not emit binary WADs. It fills a fixed JSON schema; Python owns geometry.

**Design scorer:** `configs/rubric/design_rubric.json` + `src/critic/scorer.py` scores navigation, pacing, mechanics (teach/test/twist), affordances, and narrative. Heuristics use layout JSON; vision-heavy criteria stay `unavailable` until annotation/VLM.

---

## Repository layout

```
doom-level-agent/
├── README.md                 ← keep current on every commit (see .cursor/rules)
├── requirements.txt
├── .gitignore
├── .cursor/rules/            ← project agent rules
├── proposal/
│   ├── proposal.md
│   ├── proposal.tex
│   └── proposal.pdf          ← Sep 16 one-pager
├── configs/
│   ├── schema/layout.schema.json    ← DoomLayoutV0
│   └── rubric/design_rubric.json    ← 5-pillar scorer
├── src/
│   ├── pipeline/
│   │   ├── stage1_image.py   ← concept image stub
│   │   ├── stage2_layout.py  ← Ollama → JSON
│   │   ├── stage3_build.py   ← JSON → WAD
│   │   └── validate.py
│   ├── udmf/
│   │   └── writer.py         ← TEXTMAP + minimal PWAD
│   └── critic/
│       ├── metrics.py
│       ├── scorer.py         ← design rubric
│       └── vlm_critic.py     ← stub
├── data/
│   ├── briefs/               ← text design briefs
│   ├── layouts/              ← layout JSON
│   ├── maps/                 ← generated .wad / .txt (often gitignored)
│   ├── scores/               ← rubric JSON reports (gitignored)
│   └── screenshots/
├── assets/free/              ← free textures / WADs only (no commercial IWADs)
├── patches/                  ← playtest writer / hull notes
├── scripts/
│   ├── run_pipeline.py
│   ├── hull_audit.py         ← geometry hull + portal/void probes
│   ├── score_level.py
│   └── generate_brief.py
├── tests/
│   ├── test_build.py
│   └── test_scorer.py
└── docs/                     ← extra notes as the project grows
```

---

## Status (update this table every commit)

| Area | Status | Notes |
| --- | --- | --- |
| JSON schema + validator | **done** | `configs/schema/layout.schema.json` |
| UDMF / PWAD writer | **playtested** | STEP door bottoms, self-ref solid props, L-outline portal punch |
| Stage 2 Ollama layout | **wired** | Default `qwen3-coder:30b` on william |
| Stage 1 concept image | **stub** | SVG placeholder |
| Design rubric scorer | **v0.2 strict** | Heuristic caps 3.5 / 2.5 vision; gaps count as 1.0; 4–5 need annotation/VLM |
| Hull audit | **done** | `scripts/hull_audit.py` (HALF_PORTAL_APPEARANCE, portal punch, prop void) |
| Prototype WAD | **built** | `proto_techbase_v1` + playable `brine_pump_station` / `nuclear_plant_v0` |
| VLM critic / GZDoom capture | **stub** | |
| Proposal PDF | **done** | `proposal/proposal.pdf` |
| Human eval protocol | **planned** | Final term; annotations already pluggable |
| GitHub remote | **this repo** | |

**Changelog (newest first)**

- *Hub pillars off corridor axis:* brine `pump_hub` (608,192)→(720,300); nuclear `plant_hub` (528,176)→(660,280). Rebuilt both WADs; `scripts/hull_audit.py` PASS. Notes in `patches/hub_pillar_off_axis.md`.
- *Playtest writer / hull:* keep STEP bottoms on height-mismatched doors; tall cover/pillars as self-ref solids (no hollow one-sided void); L-outline portal punch (not AABB) for full doors on wing faces; layout: brine choke cover off corridor, nuclear start cover off spawn lane, nuclear `exit_bay` clear of arena closet. `scripts/hull_audit.py` PASS on brine (29/29) and nuclear (33/33). Notes in `patches/`.
- *Classic design corpus:* detailed part-by-part refs for Entryway, Hangar, Nuclear Plant, Underhalls, House of Pain + design primer; injected into Stage 2 / path describer / strong-brief / corpus card generation (`data/corpus/classic/`, `scripts/dump_classic_guidance.py`, `configs/prompts/strong_describer.md`).
- *Micro-design:* schema `part_designs` / `props` / `closets`; writer emits cover blocks, elevation, walk-open monster closets; strong brief + Stage 2 must describe each part; brine rebuilt with hallway cover, hub pillar, key pedestal, arena closet.
- *Keys/locks + hub return:* YellowCard + yellow-locked door; brine critical path forces alcove→hub→arena.
- *Strong-brief pipeline:* Cursor writes rubric cards; Ollama emits JSON (`build_from_strong_brief.py`); shipped playable `brine_pump_station.wad`.
- *Corpus v1:* 10 few-shot cards (Project1 + William Ollama briefs + 8 contrasting themes); `generate_corpus_cards.py`; Stage 2 pulls few-shots via `corpus.fewshot`.
- *Critical path agent:* classic WAD parser + key-aware sector BFS, clarity score, template/Ollama briefs; corpus cards for Project1/William; hooked into `score_layout`.
- *Author corpus:* copied `Project1.wad` / `William.wad` into `data/corpus/wads/` with stub cards for few-shot briefs.
- *Scorer v0.2:* stricter heuristics (caps 3.5 / 2.5 vision), complexity penalty for tiny maps, `overall_with_gaps`; proto_techbase ~1.7/5 not ~4.4.
- *UZDoom local runtime:* `doom/uzdoom.exe` + root `Doom2.wad` (gitignored); `scripts/play_level.py` smoke-loads `proto_techbase_v1.wad`.
- *Playable corridor stitch:* builder inserts corridor sectors and two-sided openings; shipped `proto_techbase_v1` layout/WAD (~4.37/5 rubric).
- *Design scorer:* five-pillar rubric (navigation, pacing, teach/test/twist, affordances, narrative) with JSON heuristics + annotation overrides; `scripts/score_level.py` and `--score` on the pipeline.
- *Initial public scaffold:* schema, UDMF builder, pipeline stubs, proposal TeX/PDF, brief generator, README + Cursor rule to refresh README each commit.

---

## Quick start

### Requirements

- Python 3.10+
- Optional: [Ollama](https://ollama.com/) with a coding model (e.g. `qwen3-coder:30b`)
- Optional: Ultimate Doom Builder, GZDoom, [Freedoom](https://freedoom.github.io/) IWAD

### Install

```bash
git clone https://github.com/wang3ng/doom-level-agent.git
cd doom-level-agent
python -m pip install -r requirements.txt
```

### Build the sample layout (no LLM)

```bash
python tests/test_build.py
python scripts/run_pipeline.py --layout data/layouts/proto_techbase_v1.json \
  --out data/maps/proto_techbase_v1.wad --score
python scripts/run_pipeline.py --layout data/layouts/brine_pump_station.json \
  --out data/maps/brine_pump_station.wad
python scripts/run_pipeline.py --layout data/layouts/nuclear_plant_v0.json \
  --out data/maps/nuclear_plant_v0.wad
python scripts/hull_audit.py
```

Play in GZDoom (Freedoom IWAD), e.g.:

```bash
gzdoom -iwad path/to/freedoom2.wad -file data/maps/proto_techbase_v1.wad
```

Or with the local **UZDoom** install (repo-local; not committed):

```bash
python scripts/play_level.py
# smoke check (load + quit):
python scripts/play_level.py --smoke
```

Defaults: `doom/uzdoom.exe`, `Doom2.wad`, `data/maps/proto_techbase_v1.wad`. Or open the same `.wad` in Ultimate Doom Builder (UDMF).

## Critical path analysis

Extract a standard solution path from a classic WAD or layout JSON, score path clarity, and write a specific brief:

```bash
python scripts/analyze_path.py --wad data/corpus/wads/Project1.wad --card-out data/corpus/cards/project1.json
python scripts/analyze_path.py --wad data/corpus/wads/William.wad --card-out data/corpus/cards/william.json
# richer prose via Ollama (on william):
python scripts/analyze_path.py --wad data/corpus/wads/Project1.wad --ollama --card-out data/corpus/cards/project1.json
```

`score_layout()` also reports `critical_path_score` for generated JSON maps.

### Score a layout (design rubric)

```bash
python tests/test_scorer.py
python scripts/score_level.py --layout data/layouts/proto_two_rooms.json
python scripts/run_pipeline.py --layout data/layouts/proto_two_rooms.json --score
```

Optional human/VLM overrides:

```bash
python scripts/score_level.py --layout data/layouts/proto_two_rooms.json \
  --annotations path/to/annotations.json
```

Annotation shape: `{ "mechanic_utilization": { "subversion": { "score": 4, "notes": "..." } } }` (0–5 scale).

## Layout JSON (v0)

See [`configs/schema/layout.schema.json`](configs/schema/layout.schema.json).

Minimum shape:

```json
{
  "name": "proto_two_rooms",
  "theme": "techbase",
  "brief": "...",
  "rooms": [
    { "id": "start", "x": 0, "y": 0, "w": 256, "h": 256 }
  ],
  "connections": [
    { "a": "start", "b": "arena", "kind": "corridor", "width": 64 }
  ],
  "things": [
    { "type": "Player1Start", "x": 128, "y": 128, "angle": 0 }
  ]
}
```

Validators require exactly one `Player1Start` and a connected room graph. Graph connectivity is not yet the same as playable geometry (rooms may still be separate sectors until corridor stitching lands).

---

## Course deliverables

| Date | Artifact |
| --- | --- |
| Sep 16 | Proposal one-pager (abstract 200–300 words + mid/final plans) |
| Oct 19 | Mid report (≤4 pp NeurIPS 2026) + in-class talk |
| Dec 9 | Final poster |
| Dec 15 | Final report (≤8 pp NeurIPS 2026) |

Source: [`proposal/`](proposal/).

---

## Assets and license

- **Code:** intended for course use; keep commercial Doom IWADs out of the tree.
- **Runtime assets:** Freedoom or other free WADs/textures only under `assets/free/`.
- Do not commit secrets, ngrok URLs with credentials, or private API keys.

---
