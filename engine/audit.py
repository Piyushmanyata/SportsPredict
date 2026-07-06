"""Feedback-loop math (spec §9): outcome decoding, calibration vs
self-expected Brier, probability-band decomposition, RBP scoreboard.

All probabilities here are DECIMALS 0-1 (read endpoints return decimals —
x100 only when comparing to submitted integers).
"""

from __future__ import annotations

import math

from engine.constants import BRIER_SD_PER_MARKET, STAGE_WEIGHTS


def decode_outcome(p: float, brier: float, eps: float = 1e-4) -> int | None:
    """o = 1 iff (p-1)^2 == brier (within eps), else 0. None only at p=0.50
    (undefined — hence D3's 'avoid exactly 50'). No web lookups needed."""
    if abs(p - 0.5) < 1e-9:
        return None
    if abs((p - 1.0) ** 2 - brier) < eps:
        return 1
    if abs(p ** 2 - brier) < eps:
        return 0
    # tolerance fallback: nearest of the two candidates
    return 1 if abs((p - 1.0) ** 2 - brier) < abs(p ** 2 - brier) else 0


def self_expected_brier(ps: list[float]) -> float:
    """Right benchmark (§9.1): sum p(1-p)/n — never compare to 0.25."""
    return sum(p * (1.0 - p) for p in ps) / len(ps)


def noise_band(n: int, sd: float = BRIER_SD_PER_MARKET) -> float:
    """sd of the mean Brier ~ sd/sqrt(n). React only beyond ~1.5 bands;
    recalibrate a class only at n >= 30 with drift beyond the band."""
    return sd / math.sqrt(n)


def calibration_verdict(realized: float, expected: float, n: int) -> dict:
    """Gap in sigma across the documented 0.12-0.18 sd range (§9.1/§14.6)."""
    gap = realized - expected
    lo = gap / noise_band(n, 0.18)
    hi = gap / noise_band(n, 0.12)
    worst = max(abs(lo), abs(hi))
    verdict = "GREEN" if worst < 1.0 else ("AMBER" if worst < 2.0 else "RED")
    return {"gap": gap, "sigma_low": lo, "sigma_high": hi, "verdict": verdict,
            "note": "react only beyond ~1.5 bands; class recalibration needs n>=30"}


def band_decomposition(records: list[dict], band_width: int = 10) -> dict:
    """~10pt probability-band table (§9.5.2). records: [{'p': 0-1 decimal,
    'brier': float}] (outcome decoded internally). Returns
    {band_label: {n, avg_predicted, hit_rate, gap_pts}} — gap>0 = band cold
    (underpriced), gap<0 = band hot (overpriced)."""
    bands: dict[str, dict] = {}
    for r in records:
        o = decode_outcome(r["p"], r["brier"])
        if o is None:
            continue
        lo = int(r["p"] * 100) // band_width * band_width
        label = f"{lo}-{lo + band_width - 1}"
        b = bands.setdefault(label, {"n": 0, "sum_p": 0.0, "hits": 0})
        b["n"] += 1
        b["sum_p"] += r["p"] * 100
        b["hits"] += o
    out = {}
    for label, b in sorted(bands.items(), key=lambda kv: int(kv[0].split("-")[0])):
        avg_p = b["sum_p"] / b["n"]
        hit = 100.0 * b["hits"] / b["n"]
        out[label] = {"n": b["n"], "avg_predicted": round(avg_p, 1),
                      "hit_rate": round(hit, 1), "gap_pts": round(hit - avg_p, 1)}
    return out


# --- §9.6 RBP math (contest objective, D12) ---

def rbp(crowd_brier: float, your_brier: float, stage: str = "group") -> float:
    """(crowd - yours) x 100 x stage_weight; positive = you beat the crowd."""
    return (crowd_brier - your_brier) * 100.0 * STAGE_WEIGHTS[stage]


def rbp_scoreboard(rows: list[dict]) -> dict:
    """rows: [{'match', 'your_brier', 'crowd_brier', 'stage'}]. Returns the
    §8.4 block fields. If crowd data is missing, report RBP unavailable —
    never invent it."""
    usable = [r for r in rows if r.get("crowd_brier") is not None]
    if not usable:
        return {"status": "RBP unavailable — crowd_brier missing; run §9.5 raw audit"}
    per_match: dict[str, float] = {}
    beat = 0
    for r in usable:
        v = rbp(r["crowd_brier"], r["your_brier"], r.get("stage", "group"))
        per_match[r["match"]] = per_match.get(r["match"], 0.0) + v
        beat += r["your_brier"] < r["crowd_brier"]
    total = sum(per_match.values())
    best = max(per_match, key=per_match.get)
    worst = min(per_match, key=per_match.get)
    return {
        "settled_markets_audited": len(usable),
        "total_weighted_rbp": round(total, 2),
        "avg_rbp_per_market": round(total / len(usable), 3),
        "markets_beat_crowd": f"{beat}/{len(usable)}",
        "best_match_by_rbp": (best, round(per_match[best], 2)),
        "worst_match_by_rbp": (worst, round(per_match[worst], 2)),
    }
