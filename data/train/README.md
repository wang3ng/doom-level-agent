# Training pack

Two sources, one JSONL. The LLM still fills **layout JSON** only; this pack teaches that contract plus a critic that reads player comments.

| Source | What | Used for |
| --- | --- | --- |
| **Verified** | Hull-gated `data/layouts/*.json`, corpus cards, classic part_designs | Stage 2 SFT: brief → DoomLayoutV0, pillar-off-axis repair, brief-from-path |
| **Community** | idgames metadata + reviews (fixtures; live scrape when unblocked) | Critic SFT: comment → five-pillar JSON + short lessons injected into Stage 2 |

## Build (offline, no GPU)

```bash
python tests/test_train_sft.py
python scripts/scrape_idgames.py              # fixtures (default)
python scripts/build_sft_pack.py              # data/train/sft.jsonl
# live harvest on william if Cloudflare is not in the way:
python scripts/scrape_idgames.py --live --out data/train/cache/idgames_files.json
```

`scripts/scrape_idgames.py --live` uses a 1 req/s crawl of public idgames **frontend** pages (and the JSON API when `--id` is passed). It does **not** download WAD zips. Emails and TEXTFILEs are stripped. If Cloudflare returns an interstitial, the script exits 2 and falls back to fixtures.

## Fine-tune (william, optional)

RTX 3060 Laptop 6 GB cannot full-finetune `qwen3-coder:30b`. Use the JSONL as:

1. **Prompt few-shot / lessons** (already wired): Stage 2 reads `community_lessons.json` when present.
2. **QLoRA on a 3B coder** (Unsloth / Axolotl) with `sft.jsonl` messages format, then `ollama create` the adapter. Keep `LAYOUT_MODEL` pointed at that tag.
3. Do **not** train on commercial IWAD lumps. Community TEXTFILEs stay truncated; reviews are short player comments.

Chat schema (one JSON object per line):

```json
{"id": "...", "source": "verified|community", "task": "layout|repair|critic|brief", "messages": [{"role":"system"},{"role":"user"},{"role":"assistant"}]}
```
