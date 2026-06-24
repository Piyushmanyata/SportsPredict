"""
Feedback loop v3 — outcome decoding, Brier calculations, RBP (§9).
No web lookup needed for outcome decoding.
"""

import math
from typing import List, Optional, Dict, Tuple


EPSILON = 1e-6


def decode_outcome(p_decimal: float, brier: float) -> Optional[int]:
    """
    §9.2 Outcome decoding from submitted probability and Brier score.
    o = 1 iff (p-1)^2 = brier (within ε), else o = 0.
    Undefined at p = 0.50 (hence D3's avoid-50 rule).
    Returns 0 or 1, or None if p ≈ 0.50 (ambiguous).

    p_decimal: submitted probability as decimal (0-1).
    brier: (p - o)^2, as returned by list_results.
    """
    if abs(p_decimal - 0.50) < 0.005:
        return None  # ambiguous — reason D3 avoids 50

    b_if_yes = (p_decimal - 1.0) ** 2
    b_if_no = (p_decimal - 0.0) ** 2

    if abs(brier - b_if_yes) < EPSILON:
        return 1
    if abs(brier - b_if_no) < EPSILON:
        return 0

    # Neither matches exactly — try with rounding tolerance
    if abs(brier - b_if_yes) < 0.001:
        return 1
    if abs(brier - b_if_no) < 0.001:
        return 0

    return None  # decode failed


def brier_score(p_decimal: float, outcome: int) -> float:
    """Brier score = (p - o)^2."""
    return (p_decimal - outcome) ** 2


def self_expected_brier(predictions: List[float]) -> float:
    """
    §9.1 Self-expected Brier = Σ p(1-p) / n.
    The correct benchmark — NOT 0.25.
    """
    if not predictions:
        return 0.25
    return sum(p * (1 - p) for p in predictions) / len(predictions)


def rbp(crowd_brier: float, your_brier: float, stage_weight: float = 1.0) -> float:
    """
    §1.1 RBP = (crowd_brier - your_brier) × 100 × stage_weight.
    Positive = you beat the crowd.
    """
    return (crowd_brier - your_brier) * 100 * stage_weight


def brier_noise_bands(n: int) -> Tuple[float, float]:
    """
    §9.1 Brier noise bands: sd ≈ 0.15/√n (use 0.12-0.18 range).
    Returns (sd_low, sd_high) = 1 band each side of mean.
    """
    sd_low = 0.12 / math.sqrt(max(1, n))
    sd_high = 0.18 / math.sqrt(max(1, n))
    return sd_low, sd_high


def calibration_sigma(gap: float, n: int) -> Tuple[float, float]:
    """
    Returns (sigma_at_sd_low, sigma_at_sd_high) = gap / noise_band.
    """
    sd_low, sd_high = brier_noise_bands(n)
    sigma_high = gap / sd_low  # higher sigma at lower sd assumption
    sigma_low = gap / sd_high
    return sigma_low, sigma_high


def calibration_verdict(gap: float, n: int) -> str:
    """
    §9.1 React only beyond ~1.5 bands.
    Returns 'GREEN' | 'AMBER' | 'RED'.
    """
    sigma_lo, sigma_hi = calibration_sigma(gap, n)
    # Use midpoint for verdict
    sigma_mid = (sigma_lo + sigma_hi) / 2.0
    if sigma_mid < 1.0:
        return "GREEN"
    if sigma_mid < 2.0:
        return "AMBER"
    return "RED"


def worst_brier_autopsy(settled: List[Dict]) -> List[Dict]:
    """
    §9.3 Top 3 worst Brier markets → one-line diagnosis.

    settled: list of {market_name, p_int, brier, match_name, archetype}
    Returns top-3 with diagnosis field added.
    """
    sorted_settled = sorted(settled, key=lambda x: x.get("brier", 0), reverse=True)
    top3 = sorted_settled[:3]

    diagnoses = [
        "bad anchor",
        "missed news/lineup",
        "wording misread",
        "tie-trap miss",
        "lambda/T misread",
        "correlated-axis hit (L8)",
        "pure noise (no fix)",
    ]

    for item in top3:
        brier = item.get("brier", 0)
        arch = item.get("archetype", 0)
        p = item.get("p_int", 50) / 100.0

        # Heuristic diagnosis based on archetype and Brier magnitude
        if arch == 12:  # drama/noisy
            item["autopsy"] = "pure noise (no fix) — noisy register market, absorb (L5)"
        elif arch == 6:  # strict comparison
            item["autopsy"] = "tie-trap miss — check if §5.4 exact table was used; crowd may have priced 50"
        elif arch in (1, 5):  # win markets
            item["autopsy"] = "lambda/T misread or bad anchor — L12 ACTIVE: near-coinflip win markets need more draw mass"
        elif arch == 8:  # player prop
            item["autopsy"] = "missed news/lineup or L10 band issue — check rotation factor and SOT band"
        elif brier > 0.5:
            item["autopsy"] = "correlated-axis hit (L8) — was MC run? if deterministic, this is the QAT-SUI class of error"
        else:
            item["autopsy"] = "pure noise (no fix) — within expected variance for this probability class"

    return top3


def probability_band_decomposition(settled: List[Dict]) -> Dict:
    """
    §9.5 Fine-grained ~10pt probability-band decomposition.

    settled: list of {p_int, brier, outcome}
    Returns band -> {n, avg_predicted, avg_hit_rate, avg_brier, self_expected, gap, sigma}
    """
    bands = {}
    band_edges = list(range(0, 100, 10)) + [100]

    for lo, hi in zip(band_edges[:-1], band_edges[1:]):
        band_key = f"{lo}-{hi}"
        items = [s for s in settled
                 if lo <= s.get("p_int", 50) < hi and s.get("outcome") is not None]
        if not items:
            bands[band_key] = None
            continue

        n = len(items)
        avg_p = sum(s["p_int"] / 100.0 for s in items) / n
        hit_rate = sum(s["outcome"] for s in items) / n
        avg_brier = sum(s["brier"] for s in items) / n
        exp_brier = self_expected_brier([s["p_int"] / 100.0 for s in items])
        gap = avg_brier - exp_brier
        sigma_lo, sigma_hi = calibration_sigma(abs(gap), n)

        bands[band_key] = {
            "n": n,
            "avg_predicted_pct": round(avg_p * 100, 1),
            "hit_rate_pct": round(hit_rate * 100, 1),
            "gap_pts": round((hit_rate - avg_p) * 100, 1),
            "avg_brier": round(avg_brier, 4),
            "self_expected_brier": round(exp_brier, 4),
            "brier_gap": round(gap, 4),
            "sigma_range": f"{sigma_lo:.1f}-{sigma_hi:.1f}",
            "provisional_flag": abs(sigma_lo + sigma_hi) / 2 > 0.8,
        }

    return bands


def decode_settled_batch(predictions: List[Dict], results: List[Dict]) -> List[Dict]:
    """
    Match predictions to results and decode outcomes.

    predictions: list of prediction dicts from list_predictions
    results: list of result dicts from list_results (with brier_score)

    Returns list of enriched settled dicts.
    """
    results_by_market = {r["market_id"]: r for r in results}
    settled = []

    for pred in predictions:
        mid = pred.get("market_id")
        result = results_by_market.get(mid)
        if result is None:
            continue

        p_decimal = pred.get("probability", 0.5)  # stored as 0-1 decimal
        brier = result.get("brier_score", 0.0)
        outcome = decode_outcome(p_decimal, brier)

        settled.append({
            "market_id": mid,
            "match_id": pred.get("match_id"),
            "market_name": pred.get("market_name", ""),
            "match_name": pred.get("match_name", ""),
            "p_decimal": p_decimal,
            "p_int": int(round(p_decimal * 100)),
            "brier": brier,
            "outcome": outcome,
            "crowd_brier": result.get("crowd_brier"),
            "archetype": pred.get("archetype"),
            "stage": pred.get("stage", "group"),
        })

    return settled


def compute_rbp_scoreboard(settled: List[Dict]) -> Dict:
    """
    §8.4 RBP scoreboard from settled markets.
    Returns per-market and per-match RBP stats.
    """
    stage_weights = {"group": 1, "knockout": 2, "final": 3}

    total_weighted_rbp = 0.0
    beat_count = 0
    n_with_crowd = 0
    per_match = {}

    for s in settled:
        crowd = s.get("crowd_brier")
        if crowd is None:
            continue

        your_b = s["brier"]
        stage_w = stage_weights.get(s.get("stage", "group"), 1)
        market_rbp = rbp(crowd, your_b, stage_w)
        total_weighted_rbp += market_rbp
        beat_count += 1 if your_b < crowd else 0
        n_with_crowd += 1

        match = s.get("match_name", "unknown")
        if match not in per_match:
            per_match[match] = {"rbp": 0.0, "n": 0, "beat": 0, "stage": s.get("stage", "group")}
        per_match[match]["rbp"] += market_rbp
        per_match[match]["n"] += 1
        per_match[match]["beat"] += 1 if your_b < crowd else 0

    if n_with_crowd == 0:
        return {"available": False, "note": "crowd_brier not available in results"}

    sorted_matches = sorted(per_match.items(), key=lambda x: x[1]["rbp"], reverse=True)

    return {
        "available": True,
        "n_markets_with_crowd": n_with_crowd,
        "total_weighted_rbp": round(total_weighted_rbp, 2),
        "avg_rbp_per_market": round(total_weighted_rbp / n_with_crowd, 2),
        "beat_crowd_count": beat_count,
        "beat_crowd_rate": round(beat_count / n_with_crowd, 3),
        "best_match": sorted_matches[0] if sorted_matches else None,
        "worst_match": sorted_matches[-1] if sorted_matches else None,
        "per_match": dict(sorted_matches),
    }
