# Level corpus

## Classic references (`classic/`)

Detailed part-by-part writeups of iconic stock maps for **dense brief generation**:

| File | Map |
| --- | --- |
| `design_primer.json` | Vocabulary, rules, anti-patterns |
| `entryway.json` | Doom II MAP01 Entryway |
| `hangar.json` | Doom E1M1 Hangar |
| `nuclear_plant.json` | Doom E1M2 Nuclear Plant |
| `underhalls.json` | Doom II MAP02 Underhalls |
| `house_of_pain.json` | Doom E3M4 House of Pain |

Dump into a prompt:

```bash
python scripts/dump_classic_guidance.py --theme "techbase nukage hub key" --k 2
```

Strong Cursor cards: follow `configs/prompts/strong_describer.md`.

Loader: `src/corpus/classic.py` (wired into Stage 2, path describer, `build_from_strong_brief.py`).

## WADs (`wads/`)

Author-made classic PWADs: `Project1.wad`, `William.wad`.

## Cards (`cards/`) — briefs for few-shot generation

| Card | Role |
| --- | --- |
| project1 / william | Path-extract + Ollama from your WADs |
| brine_pump_station | Shipped hub-return + micro-design example |
| techbase_reactor, hell_keep, city_streets, key_puzzle_hub, vertical_silo, ambush_warehouse, slime_plant, nonlinear_fort | Seeded contrasting themes |

Regenerate theme cards:

```bash
python scripts/generate_corpus_cards.py --ollama
python scripts/analyze_path.py --wad data/corpus/wads/William.wad --ollama --card-out data/corpus/cards/william.json
```

Few-shot helper: `src/corpus/fewshot.py` (used by Stage 2 when `use_few_shot=True`).
