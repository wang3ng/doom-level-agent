# EN.601.762 Project Proposal

**Multimodal Agents for Doom Level Design with UDB and GZDoom**  
Fall 2026 · Due Sep 16

**Team members:** TBD  
**External collaborators:** none

## Abstract

Procedural level tools and generative models solve different halves of the same problem. Editors such as Ultimate Doom Builder (UDB) produce playable, editable maps, but they are slow to drive from language. Image and language models sketch layouts quickly, yet they rarely emit geometry that a real engine will load. We build a multimodal pipeline that keeps both sides: a brief (and optional concept image) becomes constrained layout JSON, then a deterministic compiler writes UDMF TEXTMAP into a PWAD that opens in UDB and runs in GZDoom. Stage 1 is local image generation. Stage 2 is an Ollama coding or vision-language model that fills a fixed room-connection-thing schema. Stage 3 is code, not another sample: validated JSON becomes sectors, linedefs, and things. A critic scores connectivity, player start, and monster density, and can later judge top-down rasters or GZDoom screenshots with a local VLM before asking for repair edits. Inference stays on our workstation (william; RTX 3060 Laptop, 6 GB), with models loaded one at a time, using free assets such as Freedoom. By the mid checkpoint we will show a closed loop on axis-aligned rooms and corridors, with automatic metrics and UDB/GZDoom demos. The final study adds ablations (text-only vs. text plus concept image; with vs. without critic repair), rule-based and LLM-JSON baselines, and a small human preference study on playability, clarity, and style fit. We track schema-valid compile rate, geometric proxies, and human ratings.

*(Abstract ≈ 255 words.)*

## Planned mid deliverables (Oct 19)

- JSON layout schema, validator, and UDMF/PWAD builder for axis-aligned rooms (corridors as rooms or stitched openings).
- Stage 2 layout generation from text briefs via Ollama on william (`qwen3-coder` family); concept-image stub or a first local diffusion pass if VRAM allows.
- Automatic metrics (connectivity, player start, density) on at least 10 layouts, plus a short failure gallery.
- End-to-end demo: brief → JSON → `.wad` in UDB and GZDoom (Freedoom).
- Mid report (NeurIPS 2026 format, ≤4 pages) and in-class presentation.

## Planned final deliverables (Dec 9 poster; Dec 15 report)

- Full generate-critique-repair loop with a VLM critic on layout images and/or GZDoom screenshots.
- Ablations, baselines, and a human preference study (Likert scores and pairwise comparisons).
- Documented free-asset pack and reproducible scripts on william.
- Final poster and NeurIPS-style report (≤8 pages main text).
