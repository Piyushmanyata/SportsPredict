# Session Quick Reference — v8 Final

## Mandatory Every Session (§3.2)

```
1. SYNC       list_matches(EVENT_ID) + list_predictions(LOBBY_ID) + list_results(LOBBY_ID)
2. TRIAGE     classify coverage states + horizons
3. SETTLE     decode outcomes, EB tracker, feedback loop
4. DEPTH PASS full §6.3 for every <48h match
5. SWEEP      PASS-1 for uncovered mid/far
6. REPORT     status block + after-action
```

## Verified Constants
- Event:  `aa5572ec-5930-4d99-b06b-f8966333d172`
- Lobby:  `8df8038c-fd2c-4a5f-be4e-0e11d5966c05`

## Quick Calculations (Bash)

```bash
# Devig 1X2
python run_session.py devig 1.80 3.40 5.00

# Full λ-engine + match summary
python run_session.py lambda 1.80 3.40 5.00 1.80 2.10

# L8 Monte Carlo
python run_session.py mc '[{"name":"A vs B","lam_a":1.5,"sigma_a":0.2,"lam_b":1.2,"sigma_b":0.18,"markets":["btts3plus","over_2.5","scores_ft_a"]}]'

# Strict comparison (tie-trap)
python run_session.py tie_trap corners 4.5 3.5
```

## Engine Key Rules

| Rule | Trigger | Action |
|------|---------|--------|
| **L8 MC** | >4/10 markets on same axis | batch_mc with σ=0.15λ if no source spread |
| **L10 band** | Main striker 1+SOT | Use 52-64 band; 56-70 top-half needs written driver |
| **L12 draw** | Win market, 40-60 band | Firm Dixon-Coles draw inflation; more fundamentals weight |
| **L9 ceiling** | HT-tied | Cap at 47 unless T < 2.2 |
| **L5 noisy** | Pen/red/cards | Clamp 15-85 unless anchored; stay near prior |
| **Tie trap** | "more X than" | Never hand 50; use §5.4 Bessel table |
| **D11** | Any audit proposes rule | Log as PROVISIONAL only; need n≥8 directional for ACTIVE |
| **D2** | Any shading temptation | Submit honest p; never shade toward/against crowd |

## Coverage States
- `UNCOVERED`: no predictions → urgent if <24h
- `PARTIAL`: some markets missing → top-up immediately
- `COVERED-STALE`: predicted but no Depth Pass <T-24h
- `COVERED-FRESH`: ✓

## Depth Pass Checklist (<48h, 6-10 lookups)
1. Confirmed lineup + injury check
2. Fresh odds ≤2h
3. Referee cards per game (card markets only)
4. Weather/conditions
5. Exchange cross-check (Betfair/Polymarket)
6. §5.12 overlays (altitude, rotation MD3, rest gap, winner's-slump)
7. L8 proactive MC if >4 correlated markets
8. §6.5 RBP Opportunity Pass (3 min: top-3 edges, why crowd may be wrong)

## Source Trust Order
Betfair Exchange > Pinnacle > Oddschecker/OddsPortal > single soft book

## O/U 2.5 → T Quick Table
| P(Over 2.5) | T |
|-------------|---|
| 32% | 2.0 |
| 38% | 2.2 |
| 46% | 2.5 |
| 51% | 2.7 |
| 58% | 3.0 |
| 64% | 3.3 |

## Tie Trap Reference (even matchup)
| Stat | Even p |
|------|--------|
| Fouls | 46 |
| FT corners | 43 |
| 2H corners | 41 |
| HT corners / 2H SOT | 40 |
| Cards | 39 |
| Offsides | 38 |
Dominant side: +6; weak side: −9.

## Error Handling
- `409` submit → switch to `update_prediction`
- `429` → back off 30-60s
- `403` → `join_lobby` first
- `500` → exponential backoff retry
