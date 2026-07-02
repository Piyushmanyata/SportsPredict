"""Coherence gates and the L8 correlation cap (spec section 5.11).

The ~10 markets in a match are not independent: one lambda/split misread
can poison several markets at once. batch_mc integrates over lambda
uncertainty (Normal(lambda_hat, sigma)) for any match where more than 4
of its ~10 markets load on the same latent axis, rather than submitting
deterministic point estimates on all of them.
"""

import math
import random


def check_1x2_sum(p_win, p_draw, p_loss, tol_pts=2.0):
    """1X2 triplet must sum to ~100 within tol_pts percentage points."""
    return abs((p_win + p_draw + p_loss) - 1.0) <= tol_pts / 100.0


def check_ou_monotone(probs_by_line):
    """An O/U ladder must be non-increasing as the goal line rises."""
    lines = sorted(probs_by_line)
    for lo, hi in zip(lines, lines[1:]):
        if probs_by_line[hi] > probs_by_line[lo] + 1e-9:
            return False
    return True


def check_complements(p_clean_sheet_a, p_b_scores, tol_pts=2.0):
    """Clean sheet for A and 'B scores' are complements: should sum to ~1."""
    return abs((p_clean_sheet_a + p_b_scores) - 1.0) <= tol_pts / 100.0


def check_joint_le_marginals(p_joint, p_marginal_a, p_marginal_b):
    """A joint probability may never exceed either of its marginals."""
    return p_joint <= p_marginal_a + 1e-9 and p_joint <= p_marginal_b + 1e-9


def needs_deviation_justification(p_final, p_anchor, threshold_pts=10.0):
    """A final number departing from its anchor by more than this needs a written cause."""
    return abs(p_final - p_anchor) * 100.0 > threshold_pts


def clamp_noisy_register(p, low=0.15, high=0.85, anchored=False):
    """Noisy-register markets clamp to [low, high] unless anchored by a liquid price."""
    if anchored:
        return p
    return min(high, max(low, p))


def count_correlated_axis_flag(n_markets_on_axis, n_total_markets=10):
    """L8: flag for batched MC if more than 4 of ~10 markets load on one latent axis."""
    return n_markets_on_axis > 4


def jensen_correction_fallback(observed_source_spread_pts, cap_pts=3.0):
    """Fallback widening (Jensen correction) if a flagged match is missed from the MC batch."""
    return min(cap_pts, 0.5 * observed_source_spread_pts)


def batch_mc(matches, n_draws=2000, seed=42):
    """Pure-Python reimplementation of the spec's numpy batch_mc helper.

    Integrates each flagged match's markets over Normal(lambda_hat, sigma)
    parameter uncertainty instead of a deterministic point estimate.
    """
    out = {}
    for m in matches:
        rng = random.Random(seed)
        sums = {key: 0.0 for key in m["markets"]}
        for _ in range(n_draws):
            la = max(0.05, rng.gauss(m["lam_a"], m["sigma_a"]))
            lb = max(0.05, rng.gauss(m["lam_b"], m["sigma_b"]))
            T = la + lb
            if "btts3plus" in sums:
                btts = (1 - math.exp(-la)) * (1 - math.exp(-lb))
                p11 = la * lb * math.exp(-T)
                sums["btts3plus"] += btts - p11
            if "p_2h_2plus" in sums:
                lam_2h = 0.55 * T
                sums["p_2h_2plus"] += 1 - math.exp(-lam_2h) * (1 + lam_2h)
            if "clean_sheet_a" in sums:
                sums["clean_sheet_a"] += math.exp(-lb)
            if "scores_2h_a" in sums:
                sums["scores_2h_a"] += 1 - math.exp(-0.55 * la)
        out[m["name"]] = {key: total / n_draws for key, total in sums.items()}
    return out


if __name__ == "__main__":
    assert check_1x2_sum(0.40, 0.25, 0.35) is True
    assert check_1x2_sum(0.40, 0.25, 0.30) is False
    print("check 1 (1X2 sum) OK")

    assert check_ou_monotone({1.5: 0.70, 2.5: 0.46, 3.5: 0.25}) is True
    assert check_ou_monotone({1.5: 0.70, 2.5: 0.80, 3.5: 0.25}) is False
    print("check 2 (O/U monotone) OK")

    assert check_complements(0.40, 0.60) is True
    assert check_complements(0.40, 0.50) is False
    print("check 3 (complements) OK")

    assert check_joint_le_marginals(0.20, 0.30, 0.50) is True
    assert check_joint_le_marginals(0.35, 0.30, 0.50) is False
    print("check 4 (joint <= marginals) OK")

    assert needs_deviation_justification(0.45, 0.30) is True
    assert needs_deviation_justification(0.35, 0.30) is False
    print("check 5 (deviation justification) OK")

    assert clamp_noisy_register(0.95, anchored=False) == 0.85
    assert clamp_noisy_register(0.95, anchored=True) == 0.95
    assert clamp_noisy_register(0.05) == 0.15
    print("check 6 (noisy register clamp) OK")

    assert count_correlated_axis_flag(5) is True
    assert count_correlated_axis_flag(4) is False
    print("check 7 (correlation axis flag) OK")

    assert jensen_correction_fallback(10) == 3.0
    assert jensen_correction_fallback(4) == 2.0
    print("check 8 (Jensen correction fallback) OK")

    matches = [{
        "name": "test", "lam_a": 1.5, "sigma_a": 0.0, "lam_b": 1.0, "sigma_b": 0.0,
        "markets": ["clean_sheet_a", "scores_2h_a"],
    }]
    result = batch_mc(matches, n_draws=500)["test"]
    assert abs(result["clean_sheet_a"] - math.exp(-1.0)) < 0.01
    assert abs(result["scores_2h_a"] - (1 - math.exp(-0.55 * 1.5))) < 0.01
    print("check 9 (batch_mc matches closed form at zero variance) OK")

    print("coherence.py: all checks passed")
