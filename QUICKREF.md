# Probability Cup — Session Quick Reference

Condensed operational card for `probability-cup-system-instructions-v8-final.md`
(the spec remains the authority; on any conflict, the spec wins). The `engine/`
package implements all §5/§9 math — use it instead of re-deriving tables.

## Constants (§4.3)

| Item | Value |
|---|---|
| Event | `aa5572ec-5930-4d99-b06b-f8966333d172` |
| Lobby | `8df8038c-fd2c-4a5f-be4e-0e11d5966c05` |
| Quirk | `list_events` type field is a UUID string — match by id/title |
| Shape | 48 teams · 12×4 groups · 72 group + 32 KO = 104 · Jun 11 – Jul 19 |
| Weights | group 1× · knockout 2× · final 3× |

## Prime directives, one line each (§0.2)

- **D1** zero-miss: no match uncovered at T−12h; no Depth Pass gap at T−24h.
- **D2** submit honest calibrated p — never shade, round, or hedge.
- **D3** integers 1–99; never exactly 50; last value at kickoff scores.
- **D4** never fabricate; missing data → labeled base-rate fallback, still submit.
- **D5** `list_markets` always with `match_id` (unfiltered ≈ 720 markets).
- **D6** writes via `submit_predictions_batch` (≤50); 60 req/min; 429 → 30–60s.
- **D7** hard lock = kickoff (`opening_time`), never the later `closing_time`.
- **D8** report times in IST (UTC+5:30) with date.
- **D9** numbers + sources + one-line drivers; no filler.
- **D10** no static prediction ledgers — pull live every session.
- **D11** audits propose PROVISIONAL entries only; no floors/ceilings below ACTIVE (n≥8).
- **D12** rank performance by weighted RBP, not raw Brier.

## Session loop (§3.2)

1. **SYNC** — `list_matches(event_id)` · `list_predictions(lobby_id)` · `list_results(lobby_id)`.
2. **TRIAGE** — IST deadline table; coverage states (UNCOVERED / PARTIAL / COVERED-STALE / COVERED-FRESH); horizons (<48h / ≤7d / far).
3. **SETTLE AUDIT** — decode outcomes (`engine.audit.decode_outcome`), update EB tracker (`engine/constants.py` working values), worst-3 autopsy (§9.3); deep audit (§9.5) every ~50–80 settles.
4. **DEPTH PASS** (<48h, 6–10 lookups; KO 8–12) — lineups · injuries · referee cards · weather · fresh odds ≤2h · exchange cross-check · overlays (±8 cap) · L8 MC if >4 markets share an axis (`engine.mc.batch_mc`, one batched call) · coherence gates · submit/update (Δ≥3; ≥2 post-lineup props).
5. **COVERAGE SWEEP** (mid/far) — cluster anchor harvesting, PASS-1, 12–16 matches/session.
6. **REPORT** — STATUS BLOCK (§8.1) + after-action (§8.2) + RBP block (§8.4).

## Fast paths (this repo)

```bash
# Whole-match baseline from the two anchored numbers (PASS-1 core):
python3 run_match.py --home 48 --draw 25 --away 27 --over25 51 --team-a NED --team-b JPN
# ...or straight from decimal odds (devig §5.1 applied automatically):
python3 run_match.py --odds-1x2 2.05 3.4 3.9 --odds-ou 1.95 1.87

# FULL depth-pass math in one command: fresh anchors + live markets in,
# routed prices + delta-gated update/submit payloads out (match-spec JSON
# format is in the reprice.py docstring):
python3 reprice.py --spec match.json --markets markets.json \
                   --predictions preds_dump.json

# Validate the engine against the spec's own table values + live inventory:
python3 tests/test_engine.py && python3 tests/test_markets.py
```

```python
from engine import audit, devig, goals, mc, players, thresholds, tietrap
from engine.matchsheet import build_match_sheet

devig.devig([1.28, 5.5, 9.0])            # §5.1  auto power/multiplicative
goals.t_from_over25(0.51)                 # §5.2  O/U -> T
goals.fit_split(2.7, 0.48)                # §5.2  T + 1X2 -> (lam_a, lam_b)
tietrap.p_more_exact(5.0, 4.0)            # §5.4  exact strict comparison
thresholds.ht_tied_capped(1.35, 1.35)     # §5.5  Bessel + L9 ceiling 47
players.driver_gate(66, has_driver=False) # §5.6  L10 gate on 56-70 top half
mc.batch_mc([...])                        # §5.11 L8 batched lambda-MC
audit.decode_outcome(p, brier)            # §9.2  o without web lookups
audit.rbp_scoreboard(rows)                # §9.6  RBP-first table
```

```python
# Session-loop helpers (§3.2) over raw MCP dumps — D10-safe, no stored values:
from session_tools import triage, coverage, audit_snapshot, plan_updates, chunk
from engine.markets import MatchContext, PlayerCtx, price_question
ctx = MatchContext.from_anchors("POR", "ESP", odds_1x2=[4.1, 3.6, 1.87],
                                odds_ou25=[2.0, 1.833], odds_advance=[2.8, 1.444])
price_question("Will Spain advance to the quarterfinals?", ctx)  # (66, 'advance')
```

## Engine crib (§5)

- **ANCHORED** (1X2, O/U, BTTS, scorer): 60–70% devigged anchor / 30–40% fundamentals. Power devig when overround >5% and favourite >65% (`devig.devig` decides).
- **MODELED** (splits, comparisons, obscure props): λ engine + base rates, ~50% fundamentals.
- **L12 (ACTIVE):** in the 40–60 win band, apply Dixon–Coles draw inflation firmly (+1–3 draw-flavored, −1–2 BTTS/overs; combined cap ±3, log `overdispersion-tilt`). No floors.
- **L10 (ACTIVE):** striker 1+SOT band 52–64 (60–72 retired); any modeled p in 63–70 needs a written driver, else regress (`players.driver_gate`).
- **L7:** rotation risk → discount the player's λ share, never the final output.
- **L8:** >4 markets on one latent axis → batched MC, σ = source spread or 0.15λ̂. The MC value IS the honest p.
- **L9:** HT-tied ≤47 unless anchor-implied T <2.2.
- **Noisy register** (pen/red/2H-card/offside/HT-SOT/leads-at-HT): clamp 15–85 unless anchored, label LOW, absorb ugly Briers (L5).
- **Coherence before every batch** (`engine.coherence`): 1X2 = 100±2 · O/U monotone · complements · joint ≤ marginals · |final−anchor|>10 needs written cause.

## Knockout module (now live — R32 began ~Jun 29; today is inside KO stage)

- **Wording:** "win the match" = regulation win unless clearly "advance"; if ambiguous, price regulation and flag it (§11.1).
- Stage weight 2× (final 3×): exchange/Polymarket cross-check **mandatory**; L8 MC fires for essentially every KO match.
- **Rank-aware endgame (§11.2):** ask the user for current rank/percentile; stay truth-mode unless the user explicitly flips VARIANCE MODE (§11.3 — it burns EV = −100d² per market; correlated baskets only, ≤2 matches).
- 2-bot barbell (§11.4) requires user action in-app.

## Reporting skeletons

**STATUS BLOCK** (§8.1): settled since last + session Brier vs self-expected → near-horizon table → mid/far states → actions → flags → NEXT CHECK-IN BY (IST).

**RBP scoreboard** (§8.4): settled n · total weighted RBP · avg/market · beat-crowd k/n · best/worst match by RBP (raw-Brier best clearly secondary). If crowd data missing: report `RBP unavailable` — never invent it (`audit.rbp_scoreboard` does both).

**Calibration verdict** (§9.1): compare to self-expected Σp(1−p)/n, sd ≈ 0.15/√n (quote 0.12–0.18 range); react only beyond ~1.5σ; class recalibration needs n≥30 (`audit.calibration_verdict`).

## Repo file map

```
probability-cup-system-instructions-v8-final.md   authority (v8)
QUICKREF.md                                       this card
run_match.py                                      CLI: anchors -> full archetype sheet
reprice.py                                        CLI: anchors + live markets -> routed prices + payloads
session_tools.py                                  §3.2 triage/coverage/audit/update-plan over MCP dumps
engine/constants.py                               IDs, weights, priors, gates (update EB working values here)
engine/{devig,goals,tietrap,thresholds}.py        §5.1-§5.5 math
engine/{players,jointprops}.py                    §5.6-§5.7
engine/{mc,coherence}.py                          §5.11 (L8 MC + gates)
engine/audit.py                                   §9 decode/calibration/RBP
engine/matchsheet.py                              §5.3 one-call sheet
engine/markets.py                                 MatchContext + live-question router (48-team map)
tests/test_engine.py                              pinned to the spec's table values
tests/test_markets.py                             router pinned to the live market inventory
```

Per D10: nothing in this repo stores prediction values — engine outputs are
recomputed each session; live truth comes from `list_predictions`/`list_results`.
