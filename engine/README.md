# Probability Cup engine — reusable spec math

Executable implementation of the math in
`probability-cup-system-instructions-v8-final.md` (the v8 spec). Purpose:
stop re-deriving Poisson grids, devigs, Bessel ties and audit tables by hand
every session — one command turns two anchors into a full submission-ready
market sheet, and one function turns `list_results` rows into the §9 audit.

**Doctrine guardrails are baked in:** D3 integer 1–99 / never exactly 50,
§5.9 noisy clamp 15–85 unless anchored, L9 HT-tied ceiling 47, L10 driver
gate on the 56–70 band, L6 grid floor on BTTS∧3+, §5.11 coherence gates,
±3 cap on the combined Dixon–Coles/overdispersion tilt. Nothing here shades
an output toward or away from a crowd (D2/D11).

Requires: Python 3.10+, numpy (only for `montecarlo`). Everything else is
stdlib. Verified against the spec's own published tables:

```
python3 selftest.py        # ALL CHECKS PASSED — engine matches the v8 spec tables
```

## Fast paths

### PASS-1: anchors → full market sheet (§6.1)

```
# from raw decimal odds (auto power-devig when overround>5% and fav>65%)
python3 run_match.py --name "MEX-RSA" --odds-1x2 1.85 3.6 4.4 --odds-ou25 1.95 1.87

# from already-devigged probabilities, with the L8 MC on top
python3 run_match.py --name "MEX-RSA" --p-1x2 48 25 27 --p-over25 51 --mc

# machine-readable (for building submit_predictions_batch payloads)
python3 run_match.py --name "MEX-RSA" --p-1x2 48 25 27 --p-over25 51 --json
```

Output: fitted T and λ split (with 1X2 reproduction error — must be ≤2 pts,
§5.2), every derivable archetype with p, submission integer and one-line
driver, coherence-gate results, and reminders. Strict comparisons print at
even matchup — apply the quality skew in the Depth Pass via
`tie_trap.p_strict_more_by_stat(stat, skew_a=...)`.

### Settle audit: `list_results` → §9.5/§9.6 report

```python
from engine.audit import SettledMarket, settle_audit, format_report
rows = [SettledMarket(match, market, p, brier, stage_weight, crowd_brier), ...]
print(format_report(settle_audit(rows)))
```

Decodes outcomes with zero web lookups (§9.2), benchmarks realized vs
self-expected Brier with the 0.12–0.18 sd range (§9.1), prints the per-match
table (dominant variance axis), 10-pt band decomposition, worst-Brier autopsy
candidates, and the RBP-first scoreboard when `crowd_brier` is available
(never invented when it isn't).

### L8 correlated baskets: one batched MC per session (§5.11)

```python
from engine.montecarlo import batch_mc
batch_mc([{"name": "QAT-SUI", "lam_a": 0.9, "lam_b": 1.6,
           "markets": ["win_a","draw","win_b","btts3plus","scores_2h_a","ht_tied"]},
          ...])   # every flagged match of the session in ONE call
```

σ defaults to the documented 0.15·λ̂ placeholder — pass `sigma_a`/`sigma_b`
from the sharp-source spread when you have it. The MC value **is** the honest
E[p]; submit it directly.

## Module map

| Module | Spec | Contents |
|---|---|---|
| `devig` | §5.1 | multiplicative + power devig (auto-select, no scipy), 60–70/30–40 anchor blend |
| `poisson` | §5.2/.2.1/.7 | fit T from O/U 2.5, fit split to 1X2, `MatchModel` closed forms, capped DC/overdispersion tilt, joint props |
| `tie_trap` | §5.4 | exact Poisson tie mass (Bessel I₀), strict `P(A>B)`, canonical stat means |
| `thresholds` | §5.5 | count tails, HT-tied Bessel, HT both-teams-SOT |
| `player_props` | §5.6 | v8 bands (52–64 striker SOT), L7 λ-allocation rotation, L10 driver gate |
| `montecarlo` | §5.11 | batched λ-uncertainty MC, Jensen-correction fallback widener |
| `coherence` | §5.11/§5.9/D3 | pre-batch gates, noisy clamp, submission formatting |
| `audit` | §9 | outcome decoding, settle/deep audit, RBP scoreboard, report formatter |
| `constants` | §4.3/§5.8/§5.9 | event/lobby IDs, EB base-rate tracker, noisy register, stage weights |

## What stays manual (by design)

Live state pulls (`list_matches`/`list_predictions`/`list_results` — D10: never
trust remembered values), research (odds, lineups, news — D4: never fabricate),
situational overlays (§5.12 judgement calls, capped ±8), the written drivers
themselves, and every submission decision. The engine computes; the doctrine
decides.
