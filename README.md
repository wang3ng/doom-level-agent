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
│ Critic            │  connectivity / density metrics · VLM stub
└───────────────────┘
```

**Design rule:** the LLM does not emit binary WADs. It fills a fixed JSON schema; Python owns geometry.

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
├── configs/schema/
│   └── layout.schema.json    ← DoomLayoutV0
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
│       └── vlm_critic.py     ← stub
├── data/
│   ├── briefs/               ← text design briefs
│   ├── layouts/              ← layout JSON
│   ├── maps/                 ← generated .wad / .txt (often gitignored)
│   └── screenshots/
├── assets/free/              ← free textures / WADs only (no commercial IWADs)
├── scripts/
│   ├── run_pipeline.py
│   └── generate_brief.py
├── tests/
│   └── test_build.py
└── docs/                     ← extra notes as the project grows
```

---

## Status (update this table every commit)

| Area | Status | Notes |
| --- | --- | --- |
| JSON schema + validator | **done** | `configs/schema/layout.schema.json` |
| UDMF / PWAD writer | **prototype** | Axis-aligned rooms as separate sectors; corridor *stitching* still TODO |
| Stage 2 Ollama layout | **wired** | Default `qwen3-coder:30b` on william |
| Stage 1 concept image | **stub** | SVG placeholder |
| VLM critic / GZDoom capture | **stub** | |
| Proposal PDF | **done** | `proposal/proposal.pdf` |
| Human eval protocol | **planned** | Final term |
| GitHub remote | **this repo** | |

**Changelog (newest first)**

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
python scripts/run_pipeline.py --layout data/layouts/proto_two_rooms.json
```

Outputs land under `data/maps/` (`MAP01.wad` + side-by-side `.txt` UDMF dump).

### Generate a short brief with Ollama (on william)

```bash
# on william, with Ollama running
python scripts/generate_brief.py
# → data/briefs/agent_generated.txt
```

### Brief → layout JSON → WAD (Ollama)

```bash
python scripts/run_pipeline.py \
  --brief data/briefs/proto_two_rooms.txt \
  --ollama \
  --concept
```

Environment overrides:

| Variable | Default | Meaning |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API base |
| `LAYOUT_MODEL` | `qwen3-coder:30b` | Stage 2 model |

---

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

## Development notes (william)

- GPU: NVIDIA GeForce RTX 3060 Laptop (6 GB). Load **one** heavy model at a time (coder vs VLM vs diffusion).
- Ollama models observed: `qwen3-coder:30b`, `qwen2.5-coder:32b`, `qwen2.5-coder:7b-instruct-q4_K_M`, `deepseek-coder-v2`.
- Mirror path: `~/projects/doom-level-agent`.

---

## Contributing / agent workflow

1. Make the code change.
2. **Update this README in the same commit** (Status table + Changelog entry at minimum).
3. Run `python tests/test_build.py` before pushing when touching the builder or schema.
4. Prefer small, reviewable commits.

Cursor enforces the README habit via [`.cursor/rules/readme-every-commit.mdc`](.cursor/rules/readme-every-commit.mdc).
