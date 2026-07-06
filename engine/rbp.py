"""§1.1/§9 scoring math, RBP, outcome decoding, and the feedback-loop stats.

All probabilities here are 0-1 decimals (as returned by list_predictions/
list_results); the platform's submitted integers are p/100.
"""
import math

STAGE_WEIGHTS = {"group": 1, "knockout": 2, "final": 3}


def brier(p, outcome):
    return (p - outcome) ** 2


def rbp(crowd_brier, your_brier, stage_weight=1):
    return (crowd_brier - your_brier) * 100 * stage_weight


def self_expected(ps):
    """Sigma p(1-p)/n -- the calibration benchmark, NOT 0.25 (§9.1)."""
    ps = list(ps)
    if not ps:
        return 0.0
    return sum(p * (1 - p) for p in ps) / len(ps)


def decode_outcome(p, brier_score, eps=1e-6):
    """§9.2: o=1 iff (p-1)^2 == brier (within eps), else o=0. Undefined only
    at p=0.5 (hence D3's 'avoid exactly 50')."""
    if abs(p - 0.5) < eps:
        return None
    return 1 if abs((p - 1) ** 2 - brier_score) < eps else 0


def noise_band(n, sd=0.15):
    """sd of the mean ~= sd/sqrt(n). Use 0.12-0.18 explicitly when n is small
    enough that the choice matters (§9.1)."""
    if n <= 0:
        return float("inf")
    return sd / math.sqrt(n)


def sigma_gap(realized, expected, n, sd=0.15):
    band = noise_band(n, sd)
    gap = realized - expected
    return {"gap": gap, "band": band, "sigma": gap / band if band else float("inf")}


def match_rbp_summary(market_rows):
    """market_rows: list of {"your_brier": f, "crowd_brier": f, "stage_weight": i}
    Returns the §9.6 per-match aggregation."""
    n = len(market_rows)
    if n == 0:
        return None
    weighted_rbp = [rbp(r["crowd_brier"], r["your_brier"], r.get("stage_weight", 1)) for r in market_rows]
    beat = [r["your_brier"] < r["crowd_brier"] for r in market_rows]
    return {
        "match_rbp": sum(weighted_rbp),
        "match_avg_rbp": sum(weighted_rbp) / n,
        "beat_rate": sum(beat) / n,
        "your_avg_brier": sum(r["your_brier"] for r in market_rows) / n,
        "crowd_avg_brier": sum(r["crowd_brier"] for r in market_rows) / n,
        "edge_gap": sum(r["crowd_brier"] for r in market_rows) / n - sum(r["your_brier"] for r in market_rows) / n,
    }
