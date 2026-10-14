# Plan directions

Working plan for doom-level-agent after the brine / nuclear playtests. The thesis: the bottleneck is not prompting, it is the lack of a checkable contract between the generator and the engine. The LLM is a swappable component; the contribution is the representation, the verified compiler, the metrics, and the repair loop.

Priority order: **playable → trajectory → design → diversity**. Do not work on a later layer while an earlier one is unreliable.

---

## 1. Intermediate representation: critical-path graph (Riedl)

Grounding: Riedl's experience management and GAME FORGE treat story as progression through space, encoded as a plot graph (precedence constraints + mutually exclusive branches) laid out as "islands and bridges".

- Add a `critical_path` block to the layout schema: ordered nodes `start → teach → key → lock → peak → exit`, each bound to a room id, plus `optional` branches attached between plot nodes.
- Compiler/validator rule: optional rooms may only attach to plot rooms or corridors between them; they must never sit on the only route between two plot nodes.
- Stage 2 emits the graph first, then geometry that realizes it.
- Supports **RQ1**: does the IR raise the finishable-map rate over flat room/connection JSON with the same model?

## 2. Verified compiler (done, keep extending)

Current gate (`src/pipeline/hull_gate.py`, `scripts/hull_audit.py`), enforced in `stage3_build.build_map`:

- room / closet overlap
- hollow props (`PROP_VOID`), props on portal midlines or approach axes
- incomplete door **and** lift openings, half-portal on short L-wing faces
- corridor clearance ≥ 32
- r=16 walkability BFS from spawn to ExitSwitch

Next:

- Key-aware BFS: treat locked doors as closed until the matching key cell is visited.
- Lift traversal check: rideable in both directions, not just walkable at the top.
- Short GZDoom smoke run (load + scripted walk) as an optional second gate.

## 3. Layered metrics

Produce one report per map (`data/scores/<name>.metrics.json`):

| Layer | How it is computed | Scale |
| --- | --- | --- |
| `playable` | hull gate, zero issues | 0 or 5 |
| `trajectory` | pass rate over the checks below | 0–5 |
| `design` | existing five-pillar rubric (heuristic caps kept) | 0–5 |
| `headline` | 0 if not playable, else 0.65·trajectory + 0.35·design | 0–5 |

Trajectory checks (from layout JSON, cheap):

- `path_reaches_exit`: critical path reaches the objective room
- `key_before_lock`: each key reachable without crossing its lock
- `weapon_before_peak`: first weapon reachable before the arena / peak room
- `early_combat_cap`: at most 1 weak enemy before the first weapon
- `lift_or_step_ok`: floor delta > 24 uses `kind: lift`
- `hub_return`: key detour returns through the hub before the gate
- `landmark_clearance`: solid props ≥ 64u from every portal midline

Vision criteria stay out of the headline until GZDoom screenshot capture exists.

Supports **RQ3**: do playable + trajectory scores agree with human fair-play outcomes better than design heuristics alone? The metric suite is only a contribution if this agreement is shown.

## 4. Verifier-guided repair loop (Rocktäschel)

Grounding: open-endedness as "novel but learnable" artifacts; self-improvement loops (Promptbreeder); cheap, harsh simulators (NetHack Learning Environment) that make iteration affordable.

- Turn each gate / trajectory failure into a structured, localized message (`code`, room id, coordinates, suggested fix class).
- Feed messages back to Stage 2 for a bounded number of rounds; log repairs-to-pass.
- Compare against free-form LLM/VLM critique of the same map.
- Supports **RQ2**: does structured feedback fix more failures per round than free-form critique?

## 5. Diversity (stretch, after 1–4 are reliable)

- Quality–diversity archive over level patterns (L-hub, lift return, key loop, nukage hero walk, closet ambush), keeping only maps that pass the gate.
- Remix classic corpus parts (Guzdial & Riedl conceptual blending) as few-shot references.
- Report diversity of the passing set, not of all samples.

---

## Evaluation plan

- Fixed brief set: 30+ briefs across themes.
- Primary metric: verified-finishable rate (gate + trajectory pass), confirmed on a subset by human fair play without cheats.
- Secondary: repairs to pass, trajectory and design scores, diversity of passing maps.
- Baselines: rule-based generator; LLM flat JSON without IR; IR without gate; IR + gate + free-form critique.
- Ablations: remove one of IR, gate, structured feedback, classic few-shot.

## Milestones

| Date | Target |
| --- | --- |
| Oct 19 (mid) | IR schema + validator; gate as hard build step with regression tests; layered metrics on 10+ maps; failure gallery labeled by check; brief → IR → verified WAD demo |
| Nov | Critical-path block in schema; key-aware BFS; repair loop v1; brief set frozen |
| Dec 9 (poster) | Baselines + ablations (RQ1, RQ2); human fair-play study (RQ3) |
| Dec 15 (report) | NeurIPS-style report; release IR, compiler, gate, metrics, briefs |

## References

- Riedl & Bulitko, *Interactive Narrative: An Intelligent Systems Approach*, AI Magazine 2013.
- Riedl, *Game AI as Storytelling* (experience management).
- Hartsook, Zook, Das, Riedl, *Toward Supporting Stories with Procedurally Generated Game Worlds* (GAME FORGE), CIG 2011.
- Guzdial & Riedl, *Automated Game Design via Conceptual Expansion*, AIIDE 2018.
- Hughes, Dennis, Parker-Holder, …, Rocktäschel, *Open-Endedness is Essential for Artificial Superhuman Intelligence*, ICML 2024.
- Fernando, …, Rocktäschel, *Promptbreeder: Self-Referential Self-Improvement via Prompt Evolution*, 2023.
- Küttler, …, Rocktäschel, *The NetHack Learning Environment*, NeurIPS 2020.
