"""Session-loop helpers (spec §3.2) — pure functions over raw MCP JSON.

Nothing here calls the network or stores prediction values (D10): each helper
takes the live output of list_matches / list_markets / list_predictions and
returns the derived tables the session loop needs.

    from session_tools import triage, audit_snapshot, plan_updates, chunk
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from engine.audit import calibration_verdict, self_expected_brier
from engine.constants import BATCH_LIMIT, LOBBY_ID, UPDATE_DELTA

IST = timezone(timedelta(hours=5, minutes=30))


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def ist(ts: str) -> str:
    """D8: report kickoff times in IST with the date."""
    return _parse(ts).astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def triage(matches: list[dict], now: datetime | None = None) -> list[dict]:
    """Horizon table: one row per match, sorted by kickoff (D1/D7 hard lock =
    opening_time)."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for m in matches:
        ko = _parse(m["opening_time"])
        h = (ko - now).total_seconds() / 3600.0
        rows.append({
            "match_id": m["id"], "name": m["name"],
            "kickoff_ist": ist(m["opening_time"]),
            "hours_to_lock": round(h, 1),
            "horizon": ("LOCKED" if h < 0 else
                        "NEAR" if h < 48 else
                        "MID" if h < 168 else "FAR"),
            "open_markets": m.get("open_market_count"),
        })
    return sorted(rows, key=lambda r: r["hours_to_lock"])


def coverage(markets: list[dict], predictions: list[dict]) -> dict:
    """Coverage state for one match's markets vs your open predictions."""
    predicted = {p["market_id"] for p in predictions}
    open_mkts = [m for m in markets if m.get("status") == "open"]
    missing = [m for m in open_mkts if m["id"] not in predicted]
    state = ("COVERED" if not missing else
             "UNCOVERED" if len(missing) == len(open_mkts) else "PARTIAL")
    return {"state": state, "open": len(open_mkts), "missing": missing}


def audit_snapshot(predictions: list[dict], worst_n: int = 3) -> dict:
    """Settle audit from a list_predictions dump (§9.1-§9.3).

    Settled rows carry brier_score; outcome decoding is implicit in the score
    so no extra lookups are needed.
    """
    settled = [p for p in predictions if p.get("brier_score") is not None]
    if not settled:
        return {"n": 0}
    n = len(settled)
    realized = sum(p["brier_score"] for p in settled) / n
    expected = self_expected_brier([p["probability"] for p in settled])
    return {
        "n": n,
        "open": sum(1 for p in predictions if p.get("market_status") == "open"),
        "realized": round(realized, 4),
        "self_expected": round(expected, 4),
        "verdict": calibration_verdict(realized, expected, n),
        "worst": [{"brier": p["brier_score"], "p": p["probability"],
                   "q": p["question"]}
                  for p in sorted(settled, key=lambda x: -x["brier_score"])[:worst_n]],
    }


def plan_updates(open_predictions: list[dict], new_prices: dict[str, int],
                 threshold: int = UPDATE_DELTA) -> list[dict]:
    """Delta-gated update plan (§6.3): only |new - old| >= threshold.

    new_prices maps market_id -> fresh honest integer p. Returns rows ready
    for update_prediction (plus context fields for the session log).
    """
    plan = []
    for pred in open_predictions:
        mid = pred["market_id"]
        if mid not in new_prices:
            continue
        new_p = new_prices[mid]
        if abs(new_p - pred["probability"]) >= threshold:
            plan.append({
                "prediction_id": pred["id"], "market_id": mid,
                "old": pred["probability"], "probability": new_p,
                "question": pred.get("question", ""),
            })
    return plan


def plan_submissions(markets: list[dict], predictions: list[dict],
                     new_prices: dict[str, int]) -> list[dict]:
    """Batch-ready payloads for open markets you have NOT yet predicted."""
    predicted = {p["market_id"] for p in predictions}
    return [{"market_id": m["id"], "lobby_id": m.get("lobby_id", LOBBY_ID),
             "probability": new_prices[m["id"]]}
            for m in markets
            if m.get("status") == "open" and m["id"] not in predicted
            and m["id"] in new_prices]


def chunk(payloads: list[dict], size: int = BATCH_LIMIT) -> list[list[dict]]:
    """D6: submit_predictions_batch takes <= 50 entries per call."""
    return [payloads[i:i + size] for i in range(0, len(payloads), size)]


def load_dump(path: str):
    """Read a saved MCP tool-result JSON dump (list_predictions etc.)."""
    with open(path) as f:
        return json.load(f)
