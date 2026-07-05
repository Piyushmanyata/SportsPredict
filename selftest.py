#!/usr/bin/env python3
"""Validate the engine against the spec's own published tables (v8 §5).

Every check compares an engine output to a number printed in
probability-cup-system-instructions-v8-final.md. Tolerance is ±1 pt (the spec
tables are rounded to integers). Run after any engine change:

  python3 selftest.py
"""

from __future__ import annotations

import math
import sys

from engine.devig import devig_power, devig_multiplicative
from engine.poisson import (MatchModel, fit_T_from_over25, fit_split_to_1x2,
                            score_grid_1x2, p_over, pois_cdf,
                            p_scores_first_and_other_scores_2h)
from engine.tie_trap import tie_mass, p_strict_more
from engine.thresholds import (p_at_least, ht_tied, ht_both_teams_sot,
                               p_cards_4plus, p_cards_2h_2plus)
from engine.coherence import to_submission, clamp_noisy, run_gates
from engine.audit import decode_outcome, SettledMarket, settle_audit
from engine.montecarlo import batch_mc

FAIL = 0


def check(label: str, got: float, want: float, tol: float = 1.0):
    """got/want in probability POINTS (0-100)."""
    global FAIL
    ok = abs(got - want) <= tol
    if not ok:
        FAIL += 1
    print(f"  {'✓' if ok else '✗ FAIL'} {label}: got {got:.2f}, spec {want}")


print("§5.2 totals grid — P(over 2.5) → T → derived columns")
for p_o, T_spec, p_le2, p_00, p_2h2 in [
    (0.32, 2.0, 68, 14, 30), (0.38, 2.2, 62, 11, 34), (0.46, 2.5, 54, 8, 40),
    (0.51, 2.7, 49, 7, 44), (0.58, 3.0, 42, 5, 49), (0.64, 3.3, 36, 4, 54),
]:
    T = fit_T_from_over25(p_o)
    check(f"T from P(O2.5)={p_o}", T, T_spec, tol=0.06)
    check(f"  P(≤2 goals) @T={T_spec}", pois_cdf(2, T_spec) * 100, p_le2)
    check(f"  P(0-0) @T={T_spec}", math.exp(-T_spec) * 100, p_00, tol=1.5)
    lam2h = 0.55 * T_spec
    check(f"  P(2H ≥2) @T={T_spec}", (1 - math.exp(-lam2h) * (1 + lam2h)) * 100, p_2h2)

print("\n§5.2 splits — even grid + 'calibrate to reproduce the devigged 1X2, not the labels'")
w, d, l = score_grid_1x2(1.35, 1.35)
check("even split 1.35/1.35 win", w * 100, 37)
check("even split 1.35/1.35 draw", d * 100, 26)
# The skewed reference labels (1.65/1.05 ≈ 48/25/27, 2.0/0.75 ≈ 60/16/24) are
# market-line illustrations; 60/16/24 is NOT reachable by independent Poisson
# (too little draw mass for the win/loss gap — the Dixon–Coles/L12 point).
# What §5.2 mandates is that the FIT reproduces a devigged 1X2 within ±2 pts:
la, lb = fit_split_to_1x2(2.7, 0.48, 0.27)
w, d, l = score_grid_1x2(la, lb)
check("fit T=2.7 → 48/25/27 reproduced (win)", w * 100, 48, tol=2.0)
check("fit T=2.7 → 48/25/27 reproduced (loss)", l * 100, 27, tol=2.0)
check("fitted λ_A near reference 1.65 label", la, 1.65, tol=0.15)

print("\n§5.2 BTTS / combo grid")
for la, lb, btts_s, p11_s, b3_s in [(1.35, 1.35, 55, 12, 43), (1.65, 1.05, 52, 12, 41),
                                    (2.0, 0.75, 46, 10, 36), (2.4, 0.55, 38, 7, 32)]:
    m = MatchModel("t", la, lb)
    check(f"BTTS {la}/{lb}", m.p_btts() * 100, btts_s)
    check(f"P(1-1) {la}/{lb}", m.p_1_1() * 100, p11_s)
    check(f"BTTS∧3+ {la}/{lb}", m.p_btts_and_3plus() * 100, b3_s)

print("\n§5.4 tie-trap exact tie mass + even-matchup 'A more'")
for stat_m, tie_s, more_s in [(11.0, 8.6, 46), (4.5, 13.5, 43), (2.4, 18.8, 41),
                              (2.1, 20.2, 40), (2.0, 20.7, 40), (1.8, 21.9, 39),
                              (1.5, 24.3, 38)]:
    t = tie_mass(stat_m)
    check(f"tie mass m={stat_m}", t * 100, tie_s, tol=0.2)
    check(f"even 'A more' m={stat_m}", p_strict_more(stat_m, stat_m) * 100, more_s, tol=1.0)

print("\n§5.5 cards tails (2H share 0.62)")
for lam, p4_s, p2h_s in [(2.8, 31, 52), (3.2, 40, 59), (3.5, 46, 64),
                         (4.0, 57, 71), (4.5, 66, 77)]:
    check(f"P(≥4) λ={lam}", p_cards_4plus(lam) * 100, p4_s)
    check(f"P(≥2 in 2H) λ={lam}", p_cards_2h_2plus(lam) * 100, p2h_s)

print("\n§5.5 corners / SOT / offsides tails")
for lam, want in [(3.0, 19), (4.0, 37), (5.0, 56), (6.0, 72)]:
    check(f"corners P(≥5) λ={lam}", p_at_least(5, lam) * 100, want)
for lam, want in [(1.0, 26), (2.0, 59), (3.0, 80), (4.0, 91)]:
    check(f"SOT P(≥2) λ={lam}", p_at_least(2, lam) * 100, want)
for lam, want in [(0.8, 19), (1.2, 34), (1.8, 54), (2.0, 59)]:
    check(f"offsides P(≥2) λ={lam}", p_at_least(2, lam) * 100, want)

print("\n§5.5 HT-tied Bessel table")
for la, lb, want in [(1.1, 1.1, 47), (1.25, 1.25, 44), (1.35, 1.35, 42),
                     (1.5, 1.5, 39), (1.65, 1.05, 41), (2.0, 0.75, 38), (2.4, 0.55, 34)]:
    check(f"HT-tied {la}/{lb}", ht_tied(la, lb) * 100, want)

print("\n§5.5 HT both teams ≥1 SOT")
for sa, sb, want in [(4.5, 4.5, 75), (4.0, 3.0, 62), (5.5, 3.0, 68), (6.0, 2.2, 59)]:
    check(f"HT both SOT {sa}/{sb}", ht_both_teams_sot(sa, sb) * 100, want)

print("\n§5.1 power devig")
imps = [1 / 1.30, 1 / 5.0, 1 / 9.0]  # heavy favourite + big overround
pw = devig_power(imps)
check("power devig sums to 1", sum(pw) * 100, 100, tol=0.01)
assert pw[0] > devig_multiplicative(imps)[0], "power devig should favour the favourite vs multiplicative"
print("  ✓ power > multiplicative on the favourite (boundary behaviour)")

print("\n§5.2 end-to-end anchor fit (P(O2.5)=51, 1X2=48/25/27 → mod-favourite split)")
mm = MatchModel.from_anchors("test", 0.51, 0.48, 0.25, 0.27)
check("fitted T", mm.T, 2.7, tol=0.06)
check("fitted λ_A", mm.lam_a, 1.65, tol=0.10)
assert mm.meta["fit_1x2_max_err"] <= 0.02, "1X2 reproduced within ±2 pts (§5.2)"
print(f"  ✓ 1X2 fit err {mm.meta['fit_1x2_max_err'] * 100:.2f} pts ≤ 2")

print("\n§5.7 joint prop never above either marginal")
pj = p_scores_first_and_other_scores_2h(mm, "a", "b")
assert pj <= mm.p_scores_first("a") and pj <= mm.p_scores_2h("b")
print(f"  ✓ joint {pj * 100:.1f} ≤ marginals "
      f"{mm.p_scores_first('a') * 100:.1f} / {mm.p_scores_2h('b') * 100:.1f}")

print("\n§9.2 outcome decoding")
assert decode_outcome(0.26, (0.26 - 1) ** 2) == 1        # CIV 26 → W
assert decode_outcome(0.26, 0.26 ** 2) == 0
assert decode_outcome(0.03, 0.0009) == 0                  # Enciso: o=0, well-calibrated
assert decode_outcome(0.50, 0.25) is None                 # undefined at exactly 50
print("  ✓ decode o=1/o=0/undefined-at-50 all correct (incl. the Enciso case §10.4)")

print("\n§9.5/§9.6 settle audit + RBP scoreboard smoke test")
rows = [
    SettledMarket("CAN-BIH", "win_a", 0.62, (0.62 - 1) ** 2, 1, crowd_brier=0.30),
    SettledMarket("CAN-BIH", "btts", 0.40, 0.40 ** 2, 1, crowd_brier=0.20),
    SettledMarket("QAT-SUI", "sot2h", 0.12, (0.12 - 1) ** 2, 1, crowd_brier=0.60),
]
rep = settle_audit(rows)
assert rep.n == 3 and rep.rbp is not None
assert rep.rbp["best_match_by_rbp"][0] == "CAN-BIH"
assert rep.per_match[0][0] == "QAT-SUI"  # worst brier first
print("  ✓ audit decodes, ranks matches by RBP, worst-Brier first per-match table")

print("\nD3 / §5.9 submission format + noisy clamp")
assert to_submission(0.50) in (49, 51) and to_submission(0.001) == 1 and to_submission(0.999) == 99
assert clamp_noisy(0.05, "red_card") == 0.15 and clamp_noisy(0.05, "red_card", anchored=True) == 0.05
assert clamp_noisy(0.92, "penalty_awarded") == 0.85
print("  ✓ 1–99 int, never exactly 50; noisy register clamps 15–85 unless anchored")

print("\n§5.11 coherence gates")
bad = run_gates({"win_a": 0.50, "draw": 0.30, "win_b": 0.30},
                triplet_keys=("win_a", "draw", "win_b"))
good = run_gates({"win_a": 0.48, "draw": 0.25, "win_b": 0.27},
                 triplet_keys=("win_a", "draw", "win_b"))
assert bad and not good
print("  ✓ triplet gate fires on 110-sum, passes on 100-sum")

print("\n§5.11 L8 batched MC (QAT-SUI-shaped smoke test)")
mc = batch_mc([{"name": "q", "lam_a": 0.9, "lam_b": 1.6,
                "markets": ["win_a", "draw", "win_b", "btts3plus", "scores_2h_a", "ht_tied"]}])
q = mc["q"]
check("MC triplet sums to 100", (q["win_a"] + q["draw"] + q["win_b"]) * 100, 100, tol=0.5)
det = MatchModel("q", 0.9, 1.6)
assert abs(q["scores_2h_a"] - det.p_scores_2h("a")) < 0.03  # MC ≈ point est at moderate σ
print(f"  ✓ MC coherent; scores_2h_a MC {q['scores_2h_a'] * 100:.1f} vs det {det.p_scores_2h('a') * 100:.1f}")

print()
if FAIL:
    print(f"{FAIL} CHECK(S) FAILED")
    sys.exit(1)
print("ALL CHECKS PASSED — engine matches the v8 spec tables.")
