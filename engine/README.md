# Probability Cup engine

Reusable, dependency-free (stdlib only — no pip install needed) implementation
of the math in `probability-cup-system-instructions-v8-final.md`, so a
session can call one function/CLI command instead of re-deriving formulas or
re-typing lookup tables from the spec each time.

Run `python3 -m engine.self_check` from the repo root any time — it
reproduces every worked table in the spec (totals grid, tie-trap table,
card/corner/SOT/offside tails, HT-tied, BTTS grid) from the general-purpose
functions and fails loudly on drift.

## Modules

| File | Spec section | Purpose |
|---|---|---|
| `poisson.py` | — | Poisson pmf/cdf/sf, exact tie/greater-than for two independent Poissons (pure-Python Bessel series, no scipy) |
| `devig.py` | §5.1 | implied prob, multiplicative devig, power devig (bisection), auto method selection |
| `lambda_engine.py` | §5.2 | totals grid interpolation, exact 1X2 from a lambda split, `solve_split` to back out the split that reproduces a devigged 1X2, BTTS/clean-sheet/scoring closed forms, capped DC/overdispersion tilt |
| `tie_trap.py` | §5.4 | exact tie mass + "A more than B" for any two means, not just the 7 tabulated stats |
| `thresholds.py` | §5.5 | card/corner/SOT/offside tail probabilities and HT-tied/HT-both-SOT for any lambda |
| `player_props.py` | §5.6 | goal/SOT bands (v8/L10-corrected), the 56-70 driver gate, score-or-assist multiplier, rotation-adjusted lambda (L7) |
| `mc_batch.py` | §5.11 (L8) | batched Monte Carlo over lambda uncertainty for correlated-axis matches |
| `coherence.py` | §5.11 | 1X2-sums-100, O/U monotonicity, complement, joint-<=-marginal, anchor-deviation, noisy-register clamp, correlation-axis flag, overlay cap |
| `rbp.py` | §1.1, §9 | Brier, RBP, self-expected benchmark, §9.2 outcome decoding, noise bands, per-match RBP summary |
| `constants.json` | §4.3 | event/lobby IDs, live quirks, tournament shape, stage weights, rate limits |
| `base_rates.json` | §5.8 | EB base-rate tracker working values (update in place at each settle audit) |
| `lessons_ledger.json` | §10 | L1-L15 with grade/n/band, machine-readable for gate checks |

## CLI

```
python3 -m engine.cli devig 1.85 4.20 5.50
python3 -m engine.cli totals 0.51
python3 -m engine.cli 1x2 1.65 1.05
python3 -m engine.cli split 2.7 0.48 0.27
python3 -m engine.cli tie 4.5           # even matchup
python3 -m engine.cli tie 6.0 2.2       # skewed matchup
python3 -m engine.cli threshold sot 2 2.5
python3 -m engine.cli ht-tied 1.35 1.35
python3 -m engine.cli driver-gate 0.65 --has-driver
python3 -m engine.cli rbp <crowd_brier> <your_brier> --stage-weight 2
python3 -m engine.cli decode <p> <brier>
python3 -m engine.cli mc matches.json   # see mc_batch.batch_mc docstring for schema
```

## What this does NOT do

No live odds/lineup research and no MCP calls — those still require
WebSearch/WebFetch and the SportsPredict tools each session (D4: never
fabricate). This package only removes the recompute/re-derive tax so that
work goes straight to research and coherence-checking.
