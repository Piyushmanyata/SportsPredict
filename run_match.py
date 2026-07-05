#!/usr/bin/env python3
"""PASS-1 workhorse (§6.1): devigged anchors in → full ~10-market sheet out.

Fits the λ engine from two anchored numbers (1X2 + O/U 2.5), then prints
every §5.3 archetype the engine can derive, with drivers, submission-ready
integers, and coherence-gate results. Situational overlays (§5.12), player
props (§5.6) and the L8 MC (§5.11) are layered on top — this gets a match to
COVERED-FRESH fast.

Usage (decimal odds, the common case):
  python3 run_match.py --name "MEX-RSA" --odds-1x2 1.85 3.6 4.4 --odds-ou25 1.95 1.87

Or already-devigged probabilities (0-1 or 0-100):
  python3 run_match.py --name "MEX-RSA" --p-1x2 48 25 27 --p-over25 51

Optional:
  --matchup cagey|neutral|mismatch    Dixon–Coles/overdispersion tilt context (§5.2.1)
  --mc                                also run the L8 MC with default σ=0.15λ̂
  --json                              machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys

from engine.devig import devig
from engine.poisson import MatchModel, dixon_coles_tilt, p_scores_first_and_other_scores_2h
from engine.tie_trap import p_strict_more_by_stat
from engine.thresholds import ht_tied, p_cards_4plus, p_cards_2h_2plus, p_at_least
from engine.coherence import run_gates, to_submission
from engine.constants import BASE_RATES, STAT_MEANS
from engine.montecarlo import batch_mc


def norm_p(x: float) -> float:
    return x / 100.0 if x > 1.0 else x


def build_sheet(model: MatchModel, matchup: str) -> tuple[dict, dict]:
    """Returns (markets {key: p}, drivers {key: str})."""
    w, d, l = model.p_1x2()
    m: dict[str, float] = {}
    drv: dict[str, str] = {}

    m["win_a"], m["draw"], m["win_b"] = w, d, l
    drv["win_a"] = drv["win_b"] = "devigged 1X2 via fitted λ grid (§5.2; L12: draw mass firm in 40-60 band)"
    drv["draw"] = "grid draw incl. Dixon–Coles direction (§5.2)"

    m["total_3plus"] = model.p_total_at_least(3)
    m["total_2orless"] = 1.0 - m["total_3plus"]
    drv["total_3plus"] = drv["total_2orless"] = f"Poisson T={model.T:.2f} from O/U anchor"

    m["btts"] = model.p_btts()
    m["btts_and_3plus"] = model.p_btts_and_3plus()
    drv["btts"] = f"(1-e^-λa)(1-e^-λb), split {model.lam_a:.2f}/{model.lam_b:.2f}"
    drv["btts_and_3plus"] = "BTTS − P(1-1) off the grid (L6: never below grid)"

    for t, other in (("a", "b"), ("b", "a")):
        m[f"scores_{t}"] = model.p_scores(t)
        m[f"scores_2h_{t}"] = model.p_scores_2h(t)
        m[f"clean_sheet_{t}"] = model.p_clean_sheet(t)
        drv[f"scores_{t}"] = f"1−e^-λ, λ={getattr(model, 'lam_' + t):.2f}"
        drv[f"scores_2h_{t}"] = "1−e^-(0.55λ)"
        drv[f"clean_sheet_{t}"] = f"e^-λ_{other}"

    m["2h_goals_2plus"] = model.p_2h_goals_at_least(2)
    drv["2h_goals_2plus"] = "Poisson tail on λ_2H = 0.55T"

    m["ht_tied"] = min(ht_tied(model.lam_a, model.lam_b), 0.47)  # L9 ceiling
    drv["ht_tied"] = "Bessel HT-tie (§5.5), L9 ceiling 47 applied"

    # Strict comparisons at even matchup (skew by team quality in the Depth Pass)
    for stat in ("fouls", "corners_ft", "cards", "offsides"):
        m[f"more_{stat}_a"] = p_strict_more_by_stat(stat)
        drv[f"more_{stat}_a"] = f"tie-trap engine m={STAT_MEANS[stat]} (§5.4) — even matchup; skew in Depth Pass"

    lam_cards = BASE_RATES["match_cards_mean"]
    m["cards_4plus"] = p_cards_4plus(lam_cards)
    m["cards_2h_2plus"] = p_cards_2h_2plus(lam_cards)
    drv["cards_4plus"] = drv["cards_2h_2plus"] = f"λ_cards={lam_cards} (EB tracker §5.8; ref profile in Depth Pass)"

    m["offsides_2plus_a"] = p_at_least(2, STAT_MEANS["offsides"])
    drv["offsides_2plus_a"] = "Poisson tail, per-team offsides λ=1.5 (§5.5)"

    m["pen_awarded"] = BASE_RATES["penalty_awarded"] * 0.85  # working value ≈ 29
    m["pen_or_red"] = BASE_RATES["pen_or_red"]
    drv["pen_awarded"] = drv["pen_or_red"] = "base rate + EB tracker (§5.8), noisy register LOW (L5)"

    m["a_first_and_b_2h"] = p_scores_first_and_other_scores_2h(model, "a", "b")
    drv["a_first_and_b_2h"] = "(λa/T)(1−e^-T)·P(B 2H) − haircut (§5.7)"

    tilt = dixon_coles_tilt(matchup)
    if matchup != "neutral":
        drv["_tilt"] = f"overdispersion-tilt ({matchup}): {tilt} — apply ≤±3, do not double-count (§5.2.1)"
    return m, drv


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--odds-1x2", nargs=3, type=float, metavar=("H", "D", "A"))
    ap.add_argument("--odds-ou25", nargs=2, type=float, metavar=("OVER", "UNDER"))
    ap.add_argument("--p-1x2", nargs=3, type=float, metavar=("H", "D", "A"))
    ap.add_argument("--p-over25", type=float)
    ap.add_argument("--matchup", choices=["cagey", "neutral", "mismatch"], default="neutral")
    ap.add_argument("--mc", action="store_true", help="run L8 MC (default σ=0.15λ̂)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.odds_1x2:
        p1x2, method = devig(args.odds_1x2)
    elif args.p_1x2:
        p1x2, method = [norm_p(x) for x in args.p_1x2], "pre-devigged input"
    else:
        ap.error("need --odds-1x2 or --p-1x2")
    if args.odds_ou25:
        p_over25 = devig(args.odds_ou25)[0][0]
    elif args.p_over25 is not None:
        p_over25 = norm_p(args.p_over25)
    else:
        ap.error("need --odds-ou25 or --p-over25")

    model = MatchModel.from_anchors(args.name, p_over25, *p1x2)
    markets, drivers = build_sheet(model, args.matchup)

    gates = run_gates(
        markets,
        triplet_keys=("win_a", "draw", "win_b"),
        joint_constraints=[("btts_and_3plus", "btts", "total_3plus"),
                           ("a_first_and_b_2h", "scores_a", "scores_2h_b")],
    )

    header = {
        "match": args.name,
        "devig_method": method,
        "T": round(model.T, 3),
        "split": (round(model.lam_a, 3), round(model.lam_b, 3)),
        "fit_1x2_max_err_pts": round(model.meta["fit_1x2_max_err"] * 100, 2),
        "gates": gates or "PASS",
    }

    if args.json:
        out = {**header,
               "markets": {k: {"p": round(v, 4), "submit": to_submission(v),
                               "driver": drivers.get(k, "")} for k, v in markets.items()}}
        print(json.dumps(out, indent=2))
    else:
        print(f"\n{args.name} — T={header['T']}  split={header['split']}  "
              f"devig={method}  1X2 fit err={header['fit_1x2_max_err_pts']}pts")
        if model.meta["fit_1x2_max_err"] > 0.02:
            print("  ⚠ 1X2 fit outside ±2pts — check anchors (§5.2)")
        print(f"{'market':24} {'p':>6} {'submit':>7}  driver")
        for k, v in markets.items():
            print(f"{k:24} {v * 100:6.1f} {to_submission(v):7d}  {drivers.get(k, '')}")
        if "_tilt" in drivers:
            print(f"\nTILT NOTE: {drivers['_tilt']}")
        print(f"\nCOHERENCE GATES: {'PASS' if not gates else ''}")
        for g in gates:
            print(f"  ✗ {g}")
        print("\nReminders: PASS-1 needs one fresh (≤24h) odds anchor or an explicit "
              "no-anchor label (§0.1); noisy-register markets are LOW confidence, "
              "clamped 15-85 unless anchored (§5.9); Depth Pass inside T−48h (§6.3).")

    if args.mc:
        mc = batch_mc([{"name": args.name, "lam_a": model.lam_a, "lam_b": model.lam_b,
                        "markets": ["win_a", "draw", "win_b", "total_3plus", "btts3plus",
                                    "p_2h_2plus", "scores_2h_a", "scores_2h_b", "ht_tied"]}])
        print("\nL8 MC (σ=0.15λ̂ placeholder — replace with source-spread σ when available):")
        for k, v in mc[args.name].items():
            delta = (v - markets.get({"btts3plus": "btts_and_3plus",
                                      "p_2h_2plus": "2h_goals_2plus"}.get(k, k), v)) * 100
            print(f"  {k:16} {v * 100:6.1f}  (Δ vs point estimate {delta:+.1f} pts)")
        print("  MC values ARE the honest E[p] for correlated baskets — submit directly (§5.11).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
