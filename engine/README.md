# engine/

Reusable, zero-setup (Python stdlib only, no pip install) implementation
of the probability math in `../probability-cup-system-instructions-v8-final.md`.
Exists so a session doesn't have to re-derive the lambda engine, tie-trap
formula, or Bessel tables from prose each time -- call the functions
instead.

## Layout

| File | Spec section(s) | What it does |
|---|---|---|
| `besselfn.py` | -- | Shared modified Bessel I0(x), pure series expansion |
| `devig.py` | 5.1 | Multiplicative + power devig of decimal odds |
| `lambda_engine.py` | 5.2, 5.2.1 | T/lambda derivation, closed forms, Dixon-Coles + overdispersion tilt |
| `tie_trap.py` | 5.4 | Exact tie mass for strict "more than" comparisons |
| `thresholds.py` | 5.5 | Poisson tail tables (cards/corners/SOT/offsides), HT-tied, HT-both-SOT |
| `player_props.py` | 5.6, L10 | Player goal/SOT props, v8-corrected SOT bands, L10 driver gate |
| `joint_props.py` | 5.7 | Sequence/joint props with dependence haircut |
| `base_rates.py` | 5.8 | Empirical-Bayes base-rate tracker, persists to `state/base_rate_tracker.json` |
| `coherence.py` | 5.11 | Coherence gates, L8 correlation cap, pure-Python batch Monte Carlo |
| `overlays.py` | 5.12 | Situational overlay registry, capped combined adjustment |
| `scoring.py` | 1, 9.1, 9.2 | Brier, RBP, self-expected benchmark, noise bands, outcome decode |
| `session.py` | 2.3, 2.4, 4.2, 8.1, D7/D8 | IST conversion, horizon tiers, coverage state, STATUS BLOCK |
| `taxonomy.py` | 5.3 | Lookup table: the 12 market archetypes -> which module/function handles them |
| `run_match.py` | 5.2, 6.1, 8.2 | Worked example composing the above into a full match report |
| `run_tests.py` | -- | Runs every module's self-test, prints a pass/fail summary |
| `state/*.json` | 4.3, 5.8, 10, 10.4 | Persisted constants/ledger/tracker (the only things the spec says should persist -- D10) |
| `api_reference.md` | -- | Verified SportsPredict MCP field names/schema, so sessions don't re-derive them |

Every module is independently self-contained (stdlib only, no imports of
other `engine/*.py` files, except `tie_trap.py`/`thresholds.py` importing
the shared `besselfn.py`) and ends with a self-test block using the exact
numeric tables from the spec, verified to within 0.5-2 percentage points
of the spec's own worked values.

## Usage

Run the full suite:

    python3 engine/run_tests.py

Run one module directly (also runs its self-test):

    python3 engine/tie_trap.py

Use as a library:

    import sys; sys.path.insert(0, "engine")
    import lambda_engine, devig

    p_home = devig.devig([devig.implied_prob(1.65), devig.implied_prob(3.9), devig.implied_prob(5.5)])
    T = lambda_engine.total_goals_from_over25(0.46)

End-to-end worked example (anchors in, full market table out):

    python3 engine/run_match.py engine/example_match.json

## What this does NOT do

It does not call the SportsPredict MCP tools (`list_matches`,
`submit_predictions_batch`, ...) -- that connector requires interactive
OAuth authorization the user has to grant (via their connector settings
or `/mcp`), which a non-interactive session can't do. This library only
covers the deterministic math (spec sections 1, 5, 9); the judgement
calls (situational overlays, crowd-edge research allocation, variance-mode
decisions) stay in the model's hands each session, per the spec's own D4/D11
guardrails against mechanizing anything beyond CONFIRMED, n>=30 evidence.
