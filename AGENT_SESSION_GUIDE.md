# Agent Session Guide — Jump Trading Probability Cup Bot

**Event ID:** `aa5572ec-5930-4d99-b06b-f8966333d172`  
**Lobby ID:** `8df8038c-fd2c-4a5f-be4e-0e11d5966c05`

---

## Every Session — 5-Step Protocol (§3)

### Step 1 — TRIAGE (call in parallel)
```
mcp__SportsPredict__list_matches(event_id=EVENT_ID, lobby_id=LOBBY_ID)
mcp__SportsPredict__list_predictions(lobby_id=LOBBY_ID)
mcp__SportsPredict__list_results(lobby_id=LOBBY_ID)
```
Pass all three responses to `session.ingest_triage()`. Check for urgent flags (T−12h uncovered).

### Step 2 — SETTLE AUDIT
Call `session.run_settle_audit()`. Auto-updates base rates + lesson grades. Prints deep audit if n_settled ≥ 50.

### Step 3 — DEPTH PASS (near-horizon <48h)
For each match from `session.coverage.near_horizon_not_depth_passed()`:
1. `mcp__SportsPredict__list_markets(match_id=<id>, lobby_id=LOBBY_ID)` — always match-scoped (D5)
2. Fetch fresh odds (≤2h) from external source → call `estimate_lambdas(ou25_odds, home_odds, draw_odds, away_odds)`
3. Call `session.finalize_depth_pass(match, markets, lam_h, lam_a, devigged_1x2, situational_kwargs, existing_predictions, run_l8_mc=True_if_>4_markets)`
4. Submit via batch (Step 5)

Required lookups per match (§6.3): lineups · injuries/suspensions · referee cards · weather · fresh odds ≤2h · Polymarket cross-check

### Step 4 — COVERAGE SWEEP (mid/far horizon)
Targets: 12–16 matches/session via `session.prepare_pass1_sweep()`.  
For each: `list_markets(match_id)` → `session.finalize_pass1()` → batch submit.

### Step 5 — SUBMIT BATCHES
```python
calls = build_batch(all_new_predictions, lobby_id=LOBBY_ID)
# Each call → mcp__SportsPredict__submit_predictions_batch(predictions=[...])
# On 409 → call mcp__SportsPredict__update_prediction(prediction_id, probability)
# On 429 → sleep 45s, retry
```
Max 50 per call. Max 60 calls/min total.

---

## Quality Gates (D3/D11 — checked by quality_gates_pass())
- Integer 1–99, never submit 50
- Coherence gates pass (triplet sums, ladder monotone, complements, joints ≤ marginals)
- Every market has a driver string
- Fresh odds anchor (<24h) OR labeled base-rate fallback
- Unanchored markets: p clamped 15–85

---

## Active Lessons (operative in engine)
| Lesson | Action |
|--------|--------|
| L3 | Use `archetype_strict_comparison()` (grid), not naive P(A>B) |
| L5 | Drama (pen/red): clamp 15–85, anchor at base rates |
| L8 | >4 markets on one λ axis → `run_mc_correlation()` |
| L9 | HT-tied: cap at 47 when λ_total ≥ 2.2 |
| L10 | Player SOT in 56–70 band: apply `l10_l12_corrections()` |
| L12 | Win 40–60 band: firmer Dixon–Coles draw inflation (`dixon_coles_adjust()`) |
| L14 | Overdispersion: +1pt goalless, +1pt 4+ via `dixon_coles_adjust()` |

---

## Key Config Constants
```python
from bot.config import *
EVENT_ID    # aa5572ec-5930-4d99-b06b-f8966333d172
LOBBY_ID    # 8df8038c-fd2c-4a5f-be4e-0e11d5966c05
BATCH_MAX   # 50 (D6)
STAGE_WEIGHTS  # group=1, knockout=2, final=3
```

---

## Module Reference
| Module | Key exports |
|--------|-------------|
| `bot/config.py` | Constants, thresholds |
| `bot/engine.py` | `devig_power`, `fit_lambda`, 12 archetypes, `coherence_check`, `run_mc_correlation`, `dixon_coles_adjust`, `overlay_scan` |
| `bot/session.py` | `Session`, `estimate_lambdas` — full orchestration |
| `bot/state.py` | `CoverageTracker`, `LessonsLedger`, `CalibrationRecord`, `BaseRateTracker` |
| `bot/api.py` | `build_batch`, `quality_gates_pass`, `triage_tool_calls` |
| `bot/reporting.py` | `status_block`, `after_action_report`, `rbp_scoreboard`, `deep_audit_report` |
| `bot/utils.py` | `format_ist`, `seconds_to_kickoff`, `decode_outcome_from_brier`, `clamp` |
| `main.py` | `run_session()`, self-test (`python main.py`) |

---

## RBP Formula (D12 — memorize)
```
E[RBP/market] = (crowd_brier − your_brier) × 100 × stage_weight
Submitting q = true p always maximizes expected RBP.
Never shade p toward/against crowd.
```
