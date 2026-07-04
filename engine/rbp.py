"""§1 / §9.1 / §9.6 — scoring math: Brier, RBP, noise bands."""
from .constants import STAGE_WEIGHTS


def brier(p, outcome):
    return (p - outcome) ** 2


def self_expected_brier(probs):
    """Sigma p(1-p)/n — the calibration benchmark, NOT 0.25 (§9.1)."""
    return sum(p * (1 - p) for p in probs) / len(probs)


def rbp_market(crowd_brier, your_brier, stage_weight=1):
    return (crowd_brier - your_brier) * 100 * stage_weight


def noise_band(n, sd=0.15):
    """sd of the mean ~= sd/sqrt(n); sd itself ranges 0.12-0.18 per-market (§9.1)."""
    return sd / (n ** 0.5)


def sigma_gap(realized, expected, n, sd=0.15):
    return (realized - expected) / noise_band(n, sd)


def stage_weight_for(stage):
    return STAGE_WEIGHTS[stage]


def match_rbp_summary(market_rows):
    """market_rows: iterable of dicts with keys your_brier, crowd_brier,
    stage_weight. Returns the §9.6 per-match aggregate table."""
    n = len(market_rows)
    if n == 0:
        return None
    weighted = [rbp_market(r["crowd_brier"], r["your_brier"], r.get("stage_weight", 1)) for r in market_rows]
    beat = sum(1 for r in market_rows if r["your_brier"] < r["crowd_brier"])
    return {
        "match_rbp": sum(weighted),
        "match_avg_rbp": sum(weighted) / n,
        "beat_rate": beat / n,
        "your_avg_brier": sum(r["your_brier"] for r in market_rows) / n,
        "crowd_avg_brier": sum(r["crowd_brier"] for r in market_rows) / n,
    }
