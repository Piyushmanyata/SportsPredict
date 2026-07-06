"""Validate the engine against the exact values printed in the v8 spec tables.

Run: python3 -m pytest tests/ -q   (or python3 tests/test_engine.py)
Every assertion cites the spec section it reproduces.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import audit, coherence, devig, goals, jointprops, mc, players, thresholds, tietrap


def pct(x):
    return round(100 * x)


# --- §5.2 totals grid ---
def test_totals_grid():
    for p_over, t_spec, p_le2, p_00, p_2h_2plus in [
        (0.32, 2.0, 68, 14, 30), (0.38, 2.2, 62, 11, 34), (0.46, 2.5, 54, 8, 40),
        (0.51, 2.7, 49, 7, 44), (0.58, 3.0, 42, 5, 49), (0.64, 3.3, 36, 4, 54),
    ]:
        t = goals.t_from_over25(p_over)
        assert abs(t - t_spec) < 0.06, (p_over, t)
        assert abs(pct(1 - goals.p_total_goals_geq(3, t)) - p_le2) <= 1
        assert abs(pct(math.exp(-t)) - p_00) <= 1
        assert abs(pct(goals.p_2h_goals_geq(2, t)) - p_2h_2plus) <= 1


# --- §5.2 reference splits: even case is exact; skewed labels are "~" in the
# spec, which itself says "calibrate the split to reproduce the devigged 1X2,
# not the labels" — so we test the operative fit, not the illustrative rows ---
def test_reference_splits():
    pw, pd, pl = goals.one_x_two(1.35, 1.35)
    assert (pct(pw), pct(pd), pct(pl)) == (37, 26, 37)
    # devigged 1X2 -> split -> 1X2 roundtrips within the spec's +/-2
    for target in (0.48, 0.60):
        la, lb = goals.fit_split(2.7, target)
        w, _, _ = goals.one_x_two(la, lb)
        assert abs(w - target) < 0.02 and la > lb


def test_fit_split_roundtrip():
    la, lb = goals.fit_split(2.7, 0.48)
    assert abs(la - 1.65) < 0.08 and abs(lb - 1.05) < 0.08


# --- §5.2 BTTS / combo grid ---
def test_btts_grid():
    for la, lb, btts, p11, combo in [(1.35, 1.35, 55, 12, 43), (1.65, 1.05, 52, 12, 41),
                                     (2.0, 0.75, 46, 10, 36), (2.4, 0.55, 38, 7, 32)]:
        assert abs(pct(goals.p_btts(la, lb)) - btts) <= 1
        assert abs(pct(goals.p_1_1(la, lb)) - p11) <= 1
        assert abs(pct(goals.p_btts_and_3plus(la, lb)) - combo) <= 1


# --- §5.4 tie-trap table ---
def test_tietrap_table():
    for m, tie_spec, a_more in [(11, 8.6, 46), (4.5, 13.5, 43), (2.4, 18.8, 41),
                                (2.1, 20.2, 40), (2.0, 20.7, 40), (1.8, 21.9, 39),
                                (1.5, 24.3, 38)]:
        assert abs(100 * tietrap.tie_mass(m) - tie_spec) < 0.25, m
        assert abs(pct(tietrap.p_more_even(m)) - a_more) <= 1


def test_p_more_exact_consistency():
    # equal means -> exact P(A>B) equals the even-matchup formula
    assert abs(tietrap.p_more_exact(4.5, 4.5) - tietrap.p_more_even(4.5)) < 1e-6
    # §5.4 heuristic: dominant side's 55-65 conditional split -> favored 44-52
    assert 0.44 <= tietrap.p_more_skewed(4.5, 0.55) <= 0.52
    assert 0.44 <= tietrap.p_more_skewed(4.5, 0.60) <= 0.52
    # exact form exceeds the heuristic when the mean gap is genuinely wide
    assert 0.66 <= tietrap.p_more_exact(5.5, 3.5) <= 0.72


# --- §5.5 threshold tables ---
def test_cards_tails():
    for lam, p4, p2h in [(2.8, 31, 52), (3.2, 40, 59), (3.5, 46, 64),
                         (4.0, 57, 71), (4.5, 66, 77)]:
        assert abs(pct(thresholds.p_cards_4plus(lam)) - p4) <= 1
        assert abs(pct(thresholds.p_cards_2h_2plus(lam)) - p2h) <= 1


def test_count_tails():
    for lam, p in [(3.0, 19), (4.0, 37), (5.0, 56), (6.0, 72)]:   # corners >=5
        assert abs(pct(thresholds.p_geq(5, lam)) - p) <= 1
    for lam, p in [(1.0, 26), (2.0, 59), (3.0, 80), (4.0, 91)]:   # SOT >=2
        assert abs(pct(thresholds.p_geq(2, lam)) - p) <= 1
    for lam, p in [(0.8, 19), (1.2, 34), (1.8, 54), (2.0, 59)]:   # offsides >=2
        assert abs(pct(thresholds.p_geq(2, lam)) - p) <= 1


# --- §5.5 HT-tied Bessel table (even splits keyed by T; favorites by split) ---
def test_ht_tied():
    for la, lb, spec in [(1.1, 1.1, 47), (1.25, 1.25, 44), (1.35, 1.35, 42),
                         (1.5, 1.5, 39), (1.65, 1.05, 41), (2.0, 0.75, 38),
                         (2.4, 0.55, 34)]:
        assert abs(pct(thresholds.p_ht_tied(la, lb)) - spec) <= 1, (la, lb)
    # L9 ceiling: T >= 2.2 caps at 47
    assert thresholds.ht_tied_capped(0.9, 0.9) > 47      # T=1.8: no cap
    assert thresholds.ht_tied_capped(1.1, 1.1) <= 47


def test_ht_both_sot():
    for a, b, spec in [(4.5, 4.5, 75), (4.0, 3.0, 62), (5.5, 3.0, 68), (6.0, 2.2, 59)]:
        assert abs(pct(thresholds.p_ht_both_sot(a, b)) - spec) <= 1


# --- §5.1 devig ---
def test_devig():
    r = devig.devig([2.05, 3.4, 3.9])
    assert r["method"] == "multiplicative"
    assert abs(sum(r["probs"]) - 1) < 1e-9
    # heavy favourite + big overround -> power devig, still sums to 1
    r = devig.devig([1.28, 5.5, 9.0])
    assert r["method"] == "power"
    assert abs(sum(r["probs"]) - 1) < 1e-6
    # power keeps the favourite above the naive multiplicative shrink
    mult = devig.multiplicative(devig.implied([1.28, 5.5, 9.0]))
    assert r["probs"][0] > mult[0]


# --- §5.6 / L10 ---
def test_driver_gate():
    p, note = players.driver_gate(66, has_driver=False)
    assert p < 66 and "L10" in note
    p, _ = players.driver_gate(66, has_driver=True)
    assert p == 66
    p, _ = players.driver_gate(58, has_driver=False)   # lower half: untouched
    assert p == 58


def test_player_props():
    lam = players.lam_player_goal(2.0, 0.35, rotation_factor=0.8)  # L7 lambda-side
    assert abs(lam - 0.56) < 1e-9
    assert 0 < players.p_anytime_goal(lam) < 0.45
    assert players.p_sot_1plus_2h(1.5) < players.p_sot_1plus(1.5)


# --- §5.7 ---
def test_joint():
    p_first = jointprops.p_scores_first(1.65, 2.7)
    assert 0.55 < p_first < 0.60
    j = jointprops.joint(0.5, 0.6)
    assert j <= 0.5 and abs(j - (0.30 - 0.015)) < 1e-9


# --- §5.11 MC ---
def test_batch_mc():
    res = mc.batch_mc([{"name": "X", "lam_a": 1.65, "sigma_a": mc.default_sigma(1.65),
                        "lam_b": 1.05, "sigma_b": mc.default_sigma(1.05),
                        "markets": ["btts3plus", "clean_sheet_a", "total_3plus",
                                    "ht_tied", "scores_2h_a"]}])["X"]
    det = goals.p_btts_and_3plus(1.65, 1.05)
    assert abs(res["btts3plus"] - det) < 0.03      # near deterministic value
    assert 0 < res["clean_sheet_a"] < 1 and 0 < res["ht_tied"] < 1


def test_mc_fallback_widen():
    assert mc.fallback_widen(30, 8) == (33, "lambda-uncertainty adjustment (Jensen correction) +3")
    assert mc.fallback_widen(70, 2)[0] == 69


# --- §5.11 coherence gates ---
def test_coherence():
    assert coherence.check_bounds({"a": 50})  # flags exact 50
    assert not coherence.check_bounds({"a": 49, "b": 97})
    assert coherence.check_1x2(48, 25, 30) and not coherence.check_1x2(48, 25, 27)
    assert coherence.check_ou_monotone({"2+": 60, "3+": 65})
    assert coherence.check_joint(55, 60, 50, "j")
    assert coherence.check_anchor_deviation(65, 48, None, "m")
    assert not coherence.check_anchor_deviation(65, 48, "fresh lineup news", "m")
    assert coherence.clamp_noisy(8) == 15 and coherence.clamp_noisy(8, anchored=True) == 8


# --- §9 audit math ---
def test_decode_outcome():
    # Enciso case (§10.4): p=0.03, brier=0.0009 -> o=0 (well-calibrated NO)
    assert audit.decode_outcome(0.03, 0.0009) == 0
    assert audit.decode_outcome(0.26, (0.26 - 1) ** 2) == 1   # CIV 26 -> W
    assert audit.decode_outcome(0.5, 0.25) is None


def test_calibration_verdict():
    # @118 record: 0.2326 vs 0.2173 at n=118 -> 0.92-1.38 sigma, AMBER
    v = audit.calibration_verdict(0.2326, 0.2173, 118)
    assert 0.8 < v["sigma_low"] < 1.0 and 1.3 < v["sigma_high"] < 1.5
    assert v["verdict"] == "AMBER"


def test_rbp():
    # CAN-BIH style: group-stage market where crowd is 0.10 worse -> +10 RBP
    assert abs(audit.rbp(0.30, 0.20, "group") - 10.0) < 1e-9
    assert abs(audit.rbp(0.30, 0.20, "knockout") - 20.0) < 1e-9
    board = audit.rbp_scoreboard([
        {"match": "M1", "your_brier": 0.15, "crowd_brier": 0.30, "stage": "group"},
        {"match": "M2", "your_brier": 0.30, "crowd_brier": 0.20, "stage": "group"},
    ])
    assert board["markets_beat_crowd"] == "1/2"
    assert board["best_match_by_rbp"][0] == "M1"
    assert "unavailable" in audit.rbp_scoreboard([{"match": "M", "your_brier": 0.2,
                                                   "crowd_brier": None}])["status"]


def test_band_decomposition():
    recs = [{"p": 0.62, "brier": (0.62 - 1) ** 2}, {"p": 0.65, "brier": 0.65 ** 2}]
    bands = audit.band_decomposition(recs)
    assert bands["60-69"]["n"] == 2 and bands["60-69"]["hit_rate"] == 50.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} test groups passed")
