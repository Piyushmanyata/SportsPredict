"""
Jump Trading Probability Cup — Session helpers.
Automates the §3 session protocol: triage, coverage states, batch submission,
prediction ID management, and settle audit.
Designed to be imported by the main session script or run inline via python3 -c.
"""

import re
import json
import math
from datetime import datetime, timezone, timedelta
from constants import (
    EVENT_ID, LOBBY_ID, STAGE_WEIGHTS,
    UPDATE_THRESHOLD_DEFAULT, UPDATE_THRESHOLD_POST_LINEUP,
    LESSON_ACTIVE_N,
)

# ─────────────────────────────────────────────────────────────────────────────
# Time helpers
# ─────────────────────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    return datetime.now(tz=IST)

def to_ist(dt_str: str) -> datetime:
    """Parse ISO8601 string (UTC) to IST datetime."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.astimezone(IST)

def hours_to_kickoff(opening_time_str: str) -> float:
    """Hours from now until match opening_time (kickoff)."""
    ko = to_ist(opening_time_str)
    return (ko - now_ist()).total_seconds() / 3600.0


# ─────────────────────────────────────────────────────────────────────────────
# §3.1 Coverage state classification
# ─────────────────────────────────────────────────────────────────────────────

HORIZON_NEAR = 48    # hours
HORIZON_MID  = 168   # 7 days

def classify_horizon(hours: float) -> str:
    if hours < HORIZON_NEAR:
        return "NEAR"
    if hours < HORIZON_MID:
        return "MID"
    return "FAR"

def coverage_state(match_id: str, predictions_dict: dict,
                   depth_pass_done: bool = False) -> str:
    """
    Returns one of: UNCOVERED | PARTIAL | COVERED-STALE | COVERED-FRESH.
    predictions_dict: {match_id: [prediction_objects]} from list_predictions parse.
    depth_pass_done: True if a Depth Pass has been run for this match this session.
    """
    preds = predictions_dict.get(match_id, [])
    if not preds:
        return "UNCOVERED"
    if len(preds) < 5:   # fewer than half the typical ~10 markets
        return "PARTIAL"
    if depth_pass_done:
        return "COVERED-FRESH"
    return "COVERED-STALE"


# ─────────────────────────────────────────────────────────────────────────────
# §4  Prediction-ID extraction from list_predictions raw text
# ─────────────────────────────────────────────────────────────────────────────

def parse_predictions(raw: str) -> dict:
    """
    Parse raw list_predictions tool output (JSON-like text) into a dict:
        {market_id: {"id": prediction_id, "probability": int, "match_id": str}}
    Handles the common tool-result format seen in practice.
    """
    objects = re.findall(r'\{[^{}]+\}', raw, re.DOTALL)
    result = {}
    for obj in objects:
        mid  = _re_field(obj, "market_id")
        pid  = _re_field(obj, "id")
        prob = _re_field(obj, "probability")
        maid = _re_field(obj, "match_id")
        if mid and pid and prob:
            result[mid] = {
                "id":          pid,
                "probability": int(float(prob) * 100) if float(prob) <= 1 else int(prob),
                "match_id":    maid or "",
            }
    return result

def _re_field(text: str, field: str) -> str | None:
    m = re.search(rf'"{field}"\s*:\s*"?([^",\}}\s]+)"?', text)
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# §7  Submission helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_batch(market_prob_pairs: list[tuple[str, int]],
                lobby_id: str = LOBBY_ID) -> list[dict]:
    """
    Build a submit_predictions_batch payload.
    market_prob_pairs: [(market_id, probability_int), ...]
    Returns list of dicts (≤50 per call per §D6).
    """
    return [
        {"market_id": mid, "probability": p, "lobby_id": lobby_id}
        for mid, p in market_prob_pairs
    ]

def splits_needing_update(
    new_probs: dict[str, int],
    existing: dict[str, dict],
    threshold: int = UPDATE_THRESHOLD_DEFAULT,
    post_lineup: bool = False,
) -> list[tuple[str, str, int, int]]:
    """
    Compare new_probs {market_id: new_p} against existing predictions.
    Returns list of (market_id, prediction_id, old_p, new_p) where |Δ| ≥ threshold.
    threshold drops to 2 after lineups for player props (L7, §6.3).
    """
    t = UPDATE_THRESHOLD_POST_LINEUP if post_lineup else threshold
    updates = []
    for mid, new_p in new_probs.items():
        if mid in existing:
            old_p = existing[mid]["probability"]
            if abs(new_p - old_p) >= t:
                updates.append((mid, existing[mid]["id"], old_p, new_p))
    return updates


# ─────────────────────────────────────────────────────────────────────────────
# §9  Settle-audit helpers
# ─────────────────────────────────────────────────────────────────────────────

def decode_settled(predictions: list[dict]) -> list[dict]:
    """
    Decode outcomes from settled predictions using §9.2 formula.
    Each prediction dict must have keys: probability (0–1), brier_score.
    Returns list enriched with 'outcome' ∈ {0, 1, −1}.
    """
    from engine import decode_outcome
    enriched = []
    for pred in predictions:
        p = float(pred.get("probability", 0))
        b = float(pred.get("brier_score", 0))
        pred = dict(pred)
        pred["outcome"] = decode_outcome(p, b)
        enriched.append(pred)
    return enriched

def session_brier_summary(settled: list[dict]) -> dict:
    """
    Compute realized and self-expected Brier for a list of settled predictions.
    Each dict needs: probability (0–1), brier_score.
    Returns {"n", "realized", "self_expected", "gap", "sigma_approx"}.
    """
    n = len(settled)
    if n == 0:
        return {}
    realized = sum(float(p["brier_score"]) for p in settled) / n
    self_exp = sum(
        float(p["probability"]) * (1 - float(p["probability"]))
        for p in settled
    ) / n
    # σ of mean ≈ 0.15/√n (conservative)
    sigma_of_mean = 0.15 / math.sqrt(n)
    return {
        "n":            n,
        "realized":     round(realized, 4),
        "self_expected":round(self_exp, 4),
        "gap":          round(realized - self_exp, 4),
        "sigma_approx": round(sigma_of_mean, 4),
        "sigmas":       round((realized - self_exp) / sigma_of_mean, 2),
    }

def rbp_market(crowd_brier: float, your_brier: float, stage_weight: int = 1) -> float:
    return (crowd_brier - your_brier) * 100 * stage_weight


# ─────────────────────────────────────────────────────────────────────────────
# §3.2  STATUS BLOCK formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_status_block(
    matches: list[dict],
    predictions_by_match: dict,
    settled_summary: dict | None = None,
    flags: list[str] | None = None,
) -> str:
    """
    Produce the §8.1 STATUS BLOCK string.
    matches: list of match objects from list_matches (must have opening_time, name/teams, id).
    predictions_by_match: {match_id: [preds]} from parse_predictions.
    """
    now = now_ist()
    lines = [f"STATUS — {now.strftime('%Y-%m-%d %H:%M IST')}"]

    if settled_summary:
        n, r, se, g, sig = (
            settled_summary.get("n", 0),
            settled_summary.get("realized", "?"),
            settled_summary.get("self_expected", "?"),
            settled_summary.get("gap", "?"),
            settled_summary.get("sigmas", "?"),
        )
        lines.append(
            f"Settled since last: {n} markets | "
            f"Brier {r} vs self-exp {se} | gap {g} ({sig}σ)"
        )
    else:
        lines.append("Settled since last: (not yet computed)")

    near, mid_far = [], []
    for m in matches:
        h = hours_to_kickoff(m.get("opening_time", ""))
        horizon = classify_horizon(h)
        state = coverage_state(m["id"], predictions_by_match)
        name = m.get("name") or f"{m.get('home_team','')} vs {m.get('away_team','')}"
        ko_ist = to_ist(m["opening_time"]).strftime("%d %b %H:%M IST")
        tag = f"{name} — {ko_ist} — {state}"
        if horizon == "NEAR":
            near.append(tag)
        elif horizon in ("MID", "FAR") and h < HORIZON_MID:
            mid_far.append(tag)

    lines.append("Near horizon (<48h, IST):")
    for t in near:
        lines.append(f"  {t}")
    lines.append("Mid/far horizon (≤7d, IST):")
    for t in mid_far:
        lines.append(f"  {t}")

    if flags:
        lines.append("Flags:")
        for f in flags:
            lines.append(f"  {f}")

    next_checkin = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M IST")
    lines.append(f"NEXT CHECK-IN BY: {next_checkin}  (informational — confirmed daily cadence)")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# §6.5  RBP Opportunity Pass labels
# ─────────────────────────────────────────────────────────────────────────────

def opportunity_label(your_p: int, estimated_crowd_p: int | None) -> str:
    """
    §2.5: STRONG ≥8 pts gap, MODERATE 4–7, THIN 1–3, UNKNOWN if no crowd estimate.
    This is a RESEARCH ALLOCATOR ONLY — never adjusts the submitted probability.
    """
    if estimated_crowd_p is None:
        return "UNKNOWN"
    gap = abs(your_p - estimated_crowd_p)
    if gap >= 8:
        return "STRONG"
    if gap >= 4:
        return "MODERATE"
    return "THIN"


# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    raw = '{"id":"abc123","market_id":"mkt-001","probability":0.72,"match_id":"m-1"}'
    parsed = parse_predictions(raw)
    print("parse_predictions:", parsed)

    print("hours_to_kickoff (test):", round(hours_to_kickoff("2026-06-24T20:00:00Z"), 1))

    summary = session_brier_summary([
        {"probability": 0.70, "brier_score": 0.09},
        {"probability": 0.45, "brier_score": 0.20},
    ])
    print("brier_summary:", summary)

    print("opportunity_label 42 vs 50:", opportunity_label(42, 50))
    print("opportunity_label 79 vs 82:", opportunity_label(79, 82))
