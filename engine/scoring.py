"""Scoring math: Brier, RBP, self-expected benchmark, outcome decoding (spec sections 1, 9.1, 9.2).

RBP (Relative Brier Points) is the contest's actual objective: it pays
the gap between your Brier and the crowd's Brier, not raw accuracy in
isolation. Submitting your true probability is always the Brier- and
RBP-maximizing move (D2) -- shading toward or away from an anchor or a
crowd estimate only burns expected RBP, per the cost-of-distortion table.
"""

import math

STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}


def stage_weight(stage):
    """Contest stage weight: group 1x, knockout 2x, final 3x."""
    if stage not in STAGE_WEIGHTS:
        raise ValueError(f"unknown stage: {stage!r}, expected one of {list(STAGE_WEIGHTS)}")
    return STAGE_WEIGHTS[stage]


def brier(p, o):
    """Brier score for a single binary market: (p - o) ** 2."""
    return (p - o) ** 2


def rbp(crowd_brier, your_brier, stage_wt=1):
    """Relative Brier Points for one market: (crowd_brier - your_brier) * 100 * stage_weight."""
    return (crowd_brier - your_brier) * 100 * stage_wt


def self_expected(p_list):
    """Self-expected mean Brier: mean of p*(1-p) over submitted probabilities."""
    if not p_list:
        return 0.0
    return sum(p * (1 - p) for p in p_list) / len(p_list)


def noise_band(n, sd=0.15):
    """Standard deviation of the mean Brier at sample size n: sd / sqrt(n)."""
    if n <= 0:
        return float("inf")
    return sd / math.sqrt(n)


def decode_outcome(p, brier_score, eps=1e-6):
    """Decode the realized outcome from (p, brier) alone: o=1 iff (p-1)**2 ~= brier.

    Genuinely ambiguous only at p == 0.5, where (p-1)**2 == p**2 -- the
    spec's D3 tells submitters to avoid exactly 50 for this reason. This
    function does not special-case it; it just applies the rule as stated.
    """
    return 1 if abs((p - 1) ** 2 - brier_score) < eps else 0


def expected_rbp_cost(deviation_pts):
    """Expected RBP cost of shading your submission by deviation_pts percentage points."""
    return (deviation_pts ** 2) / 100.0


def edge_identity_cost(q, p):
    """Expected RBP cost of submitting q instead of your true probability p: 100*(q-p)**2."""
    return 100 * (q - p) ** 2


if __name__ == "__main__":
    assert stage_weight("group") == 1
    assert stage_weight("knockout") == 2
    assert stage_weight("final") == 3
    try:
        stage_weight("bogus")
        raise SystemExit("expected ValueError")
    except ValueError:
        pass
    print("check 1 (stage weights) OK")

    assert abs(brier(0.7, 1) - 0.09) < 1e-9
    assert abs(brier(0.7, 0) - 0.49) < 1e-9
    print("check 2 (brier) OK")

    assert abs(rbp(0.30, 0.10, stage_wt=2) - 40.0) < 1e-9
    print("check 3 (rbp) OK")

    assert abs(self_expected([0.5, 0.5]) - 0.25) < 1e-9
    assert self_expected([]) == 0.0
    print("check 4 (self_expected) OK")

    assert abs(noise_band(10) - 0.0474) < 0.001
    assert abs(noise_band(20) - 0.0335) < 0.001
    assert abs(noise_band(50) - 0.0212) < 0.001
    assert abs(noise_band(100) - 0.015) < 0.001
    print("check 5 (noise bands) OK")

    assert decode_outcome(0.7, 0.09) == 1
    assert decode_outcome(0.7, 0.49) == 0
    print("check 6 (outcome decode) OK")

    cost_table = [(3, 0.09), (5, 0.25), (8, 0.64), (10, 1.00), (15, 2.25)]
    for deviation_pts, expected_cost in cost_table:
        assert abs(expected_rbp_cost(deviation_pts) - expected_cost) < 1e-9
        assert abs(edge_identity_cost(0.50 + deviation_pts / 100.0, 0.50) - expected_cost) < 1e-9
    print("check 7 (cost-of-distortion table) OK")

    print("scoring.py: all checks passed")
