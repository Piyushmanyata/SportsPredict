"""
Feedback loop and settle audit (§9).

Implements:
  - outcome decoding from Brier without web lookups (§9.2)
  - self-expected Brier computation (§9.1)
  - worst-Brier autopsy (§9.3)
  - RBP computation (§9.6)
  - full settle audit summary
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# §9.2 Outcome decoding
# ---------------------------------------------------------------------------

def decode_outcome(p_decimal: float, brier: float, epsilon: float = 0.001) -> int | None:
    """
    Decode binary outcome from submitted p (0-1 decimal) and Brier score.
    Returns 1 (YES) or 0 (NO), or None if p == 0.50 (ambiguous, per D3).

    Logic: o=1 iff (p−1)² ≈ b  →  (p−1)² = b when o=1
            o=0 iff p² ≈ b
    """
    if abs(p_decimal - 0.5) < 0.001:
        return None  # avoid exactly 0.5 (D3)
    if abs((p_decimal - 1.0) ** 2 - brier) < epsilon:
        return 1
    if abs(p_decimal ** 2 - brier) < epsilon:
        return 0
    # Fallback: pick whichever is closer
    err_yes = abs((p_decimal - 1.0) ** 2 - brier)
    err_no  = abs(p_decimal ** 2 - brier)
    return 1 if err_yes < err_no else 0


def compute_brier(p_decimal: float, outcome: int) -> float:
    """Brier = (p − o)²."""
    return (p_decimal - outcome) ** 2


def expected_brier(p_decimal: float) -> float:
    """Self-expected Brier = p(1-p) (variance of a Bernoulli)."""
    return p_decimal * (1 - p_decimal)


# ---------------------------------------------------------------------------
# §9.1 — aggregate calibration stats
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    n: int
    realized_brier: float
    self_expected_brier: float
    gap: float
    gap_sigma: float      # assuming sd = 0.15 (mid-range of 0.12-0.18)
    verdict: str          # GREEN / AMBER / RED

    def describe(self) -> str:
        return (
            f"n={self.n} | realized={self.realized_brier:.4f} | "
            f"expected={self.self_expected_brier:.4f} | "
            f"gap=+{self.gap:.4f} | {self.gap_sigma:.2f}σ — {self.verdict}"
        )


def brier_vs_expected(
    settled: list[dict],
    sd: float = 0.15,
) -> CalibrationResult:
    """
    Compute realized vs self-expected Brier (§9.1).

    settled: list of {p_decimal: float, brier: float}
    sd: per-market Brier sd (0.12-0.18; spec default 0.15).
    """
    n = len(settled)
    if n == 0:
        return CalibrationResult(0, 0, 0, 0, 0, "N/A")

    realized = sum(s["brier"] for s in settled) / n
    expected = sum(expected_brier(s["p_decimal"]) for s in settled) / n
    gap      = realized - expected
    noise    = sd / math.sqrt(n)
    gap_sigma = abs(gap) / noise if noise > 0 else 0

    if gap_sigma < 1.0:
        verdict = "GREEN"
    elif gap_sigma < 1.5:
        verdict = "AMBER"
    else:
        verdict = "RED"

    return CalibrationResult(
        n=n,
        realized_brier=realized,
        self_expected_brier=expected,
        gap=gap,
        gap_sigma=gap_sigma,
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# §9.6 — RBP computation
# ---------------------------------------------------------------------------

@dataclass
class RBPMarket:
    market_name: str
    p_decimal:   float
    outcome:     int
    your_brier:  float
    crowd_brier: float | None
    stage_weight: float
    rbp:         float | None   # None if crowd_brier unavailable
    beat_crowd:  bool | None

    @property
    def weighted_rbp(self) -> float | None:
        if self.rbp is None:
            return None
        return self.rbp * self.stage_weight


def compute_rbp(
    your_brier: float,
    crowd_brier: float | None,
    stage_weight: float = 1.0,
) -> float | None:
    """RBP = (crowd_brier − your_brier) × 100 × stage_weight."""
    if crowd_brier is None:
        return None
    return (crowd_brier - your_brier) * 100 * stage_weight


@dataclass
class MatchAudit:
    match_name: str
    stage_weight: float
    markets: list[RBPMarket]

    @property
    def total_weighted_rbp(self) -> float | None:
        vals = [m.weighted_rbp for m in self.markets if m.weighted_rbp is not None]
        return sum(vals) if vals else None

    @property
    def avg_your_brier(self) -> float:
        return sum(m.your_brier for m in self.markets) / len(self.markets) if self.markets else 0

    @property
    def avg_crowd_brier(self) -> float | None:
        vals = [m.crowd_brier for m in self.markets if m.crowd_brier is not None]
        return sum(vals) / len(vals) if vals else None

    @property
    def beat_rate(self) -> float | None:
        vals = [m.beat_crowd for m in self.markets if m.beat_crowd is not None]
        return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# §9.3 Worst-Brier autopsy
# ---------------------------------------------------------------------------

AUTOPSY_TAXONOMY = [
    "bad anchor",
    "missed news/lineup",
    "wording misread",
    "tie-trap miss",
    "λ/T misread",
    "correlated-axis hit (L8)",
    "pure noise (no fix)",
]


def worst_brier_autopsy(
    settled: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """
    Return top_n worst Brier records for autopsy (§9.3).
    Each record: {market_name, p_decimal, brier, outcome, diagnosis}
    Diagnosis is filled in by the agent; this just sorts and returns the list.
    """
    sorted_markets = sorted(settled, key=lambda x: x["brier"], reverse=True)
    top = sorted_markets[:top_n]
    for item in top:
        item.setdefault("diagnosis", "— fill in from §9.3 taxonomy —")
    return top


# ---------------------------------------------------------------------------
# §9.5 Probability-band decomposition
# ---------------------------------------------------------------------------

def band_decomposition(settled: list[dict]) -> list[dict]:
    """
    Break settled markets into ~10pt probability bands and compute
    realized vs predicted hit rate in each band (§9.5).

    settled: list of {p_decimal, brier, outcome (optional)}
    """
    bands = {}
    for s in settled:
        p_int = round(s["p_decimal"] * 100)
        band_lo = (p_int // 10) * 10
        band_key = f"{band_lo}-{band_lo+9}"
        if band_key not in bands:
            bands[band_key] = {"lo": band_lo, "n": 0, "sum_p": 0.0, "sum_o": 0.0}
        bands[band_key]["n"]     += 1
        bands[band_key]["sum_p"] += s["p_decimal"]
        outcome = s.get("outcome") or decode_outcome(s["p_decimal"], s["brier"])
        if outcome is not None:
            bands[band_key]["sum_o"] += outcome

    rows = []
    for key, b in sorted(bands.items(), key=lambda x: x[1]["lo"]):
        n = b["n"]
        avg_p = b["sum_p"] / n
        avg_o = b["sum_o"] / n if n > 0 else 0
        gap_pts = (avg_o - avg_p) * 100
        rows.append({
            "band":   key,
            "n":      n,
            "avg_p":  round(avg_p * 100, 1),
            "hit_pct": round(avg_o * 100, 1),
            "gap_pts": round(gap_pts, 1),
        })
    return rows


# ---------------------------------------------------------------------------
# Full settle audit summary
# ---------------------------------------------------------------------------

def settle_audit(
    settled_predictions: list[dict],
    crowd_brier_by_market: dict[str, float] | None = None,
    stage_weight: float = 1.0,
    match_name: str = "unknown",
) -> dict:
    """
    Run the full settle audit for a batch of predictions.

    settled_predictions: list of {
        market_name: str,
        p_decimal: float,      # your submitted probability (0-1)
        brier: float,          # actual Brier from platform
        crowd_brier: float | None,  # crowd Brier if available
    }
    Returns a summary dict with all key metrics.
    """
    # Decode outcomes
    for m in settled_predictions:
        if "outcome" not in m:
            m["outcome"] = decode_outcome(m["p_decimal"], m["brier"])

    # Calibration
    cal = brier_vs_expected(settled_predictions)

    # RBP
    rbp_markets = []
    for m in settled_predictions:
        cb = crowd_brier_by_market.get(m["market_name"]) if crowd_brier_by_market else m.get("crowd_brier")
        rbp = compute_rbp(m["brier"], cb, stage_weight)
        rbp_markets.append(RBPMarket(
            market_name=m["market_name"],
            p_decimal=m["p_decimal"],
            outcome=m.get("outcome"),
            your_brier=m["brier"],
            crowd_brier=cb,
            stage_weight=stage_weight,
            rbp=rbp,
            beat_crowd=(m["brier"] < cb) if cb is not None else None,
        ))

    match_audit = MatchAudit(match_name=match_name, stage_weight=stage_weight, markets=rbp_markets)

    # Worst Brier autopsy
    worst = worst_brier_autopsy(settled_predictions)

    # Band decomposition
    bands = band_decomposition(settled_predictions)

    return {
        "calibration":   cal,
        "match_audit":   match_audit,
        "worst_briers":  worst,
        "band_decomp":   bands,
    }
