"""
MCP API client wrapper with rate-limiting and error handling.

All calls go through the SportsPredict MCP tools (mcp__SportsPredict__*).
Because this runs inside Claude/MCP context, these functions are stubs that
format the correct tool calls; the actual tool invocations happen via the agent.

Rate limit: 60 req/min globally (D6). On 429 back off 30–60s.
"""

import time
from typing import Any, Dict, List, Optional

from bot.config import (
    EVENT_ID, LOBBY_ID,
    RATE_LIMIT_PER_MIN, BATCH_MAX, RATE_429_BACKOFF,
)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter: 60 req/min."""

    def __init__(self, rpm: int = RATE_LIMIT_PER_MIN):
        self.rpm = rpm
        self._calls: List[float] = []

    def wait_if_needed(self) -> None:
        now = time.monotonic()
        # Drop timestamps older than 60s
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= self.rpm:
            sleep_for = 60 - (now - self._calls[0]) + 0.1
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < 60]
        self._calls.append(time.monotonic())


_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Tool call stubs
# These functions document the exact MCP tool parameters.
# In a Claude session the actual calls are made via MCP tool use.
# ---------------------------------------------------------------------------

def call_list_events(limit: int = 25) -> Dict:
    """mcp__SportsPredict__list_events"""
    _limiter.wait_if_needed()
    return {"tool": "mcp__SportsPredict__list_events", "params": {"limit": limit}}


def call_list_matches(event_id: str = EVENT_ID, lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__list_matches — always scoped by event_id (D5)."""
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__list_matches",
        "params": {"event_id": event_id, "lobby_id": lobby_id},
    }


def call_list_markets(match_id: str, lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__list_markets — always scoped by match_id (D5)."""
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__list_markets",
        "params": {"match_id": match_id, "lobby_id": lobby_id},
    }


def call_list_predictions(lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__list_predictions."""
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__list_predictions",
        "params": {"lobby_id": lobby_id},
    }


def call_list_results(lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__list_results."""
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__list_results",
        "params": {"lobby_id": lobby_id},
    }


def call_join_lobby(lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__join_lobby — re-join fallback if membership drops."""
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__join_lobby",
        "params": {"lobby_id": lobby_id},
    }


def call_submit_prediction(market_id: str, probability: int, lobby_id: str = LOBBY_ID) -> Dict:
    """mcp__SportsPredict__submit_prediction — single market."""
    _validate_probability(probability)
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__submit_prediction",
        "params": {"market_id": market_id, "lobby_id": lobby_id, "probability": probability},
    }


def call_update_prediction(prediction_id: str, probability: int) -> Dict:
    """mcp__SportsPredict__update_prediction — for 409 'already predicted' cases."""
    _validate_probability(probability)
    _limiter.wait_if_needed()
    return {
        "tool":   "mcp__SportsPredict__update_prediction",
        "params": {"prediction_id": prediction_id, "probability": probability},
    }


def build_batch(
    markets: List[Dict],
    lobby_id: str = LOBBY_ID,
) -> List[Dict]:
    """
    Build a list of submit_predictions_batch tool calls from market dicts.
    Each market dict must have 'market_id' and 'p' (int 1-99).
    Splits into chunks of BATCH_MAX (≤50, D6).

    Returns list of tool call dicts.
    """
    chunks = [markets[i:i + BATCH_MAX] for i in range(0, len(markets), BATCH_MAX)]
    calls = []
    for chunk in chunks:
        predictions = []
        for m in chunk:
            _validate_probability(m["p"])
            predictions.append({
                "market_id": m["market_id"],
                "lobby_id":  lobby_id,
                "probability": m["p"],
            })
        calls.append({
            "tool":   "mcp__SportsPredict__submit_predictions_batch",
            "params": {"predictions": predictions},
        })
    return calls


# ---------------------------------------------------------------------------
# Quality gate helpers (§0.1 / §5.11)
# ---------------------------------------------------------------------------

def _validate_probability(p: int) -> None:
    """Raise if p not integer in 1–99 (D3)."""
    if not isinstance(p, int):
        raise ValueError(f"Probability must be int, got {type(p).__name__}: {p}")
    if not (1 <= p <= 99):
        raise ValueError(f"Probability {p} out of range 1–99")


def quality_gates_pass(market: Dict) -> tuple:
    """
    §0.1 quality gates — returns (passed: bool, violations: list[str]).
    market dict keys: p, driver, anchored, coherence_violations, research_tier.
    """
    violations = []

    # (a) integer 1–99
    try:
        _validate_probability(market.get("p", 0))
    except ValueError as e:
        violations.append(str(e))

    # (b) coherence gates (already run by caller)
    for v in market.get("coherence_violations", []):
        violations.append(f"coherence: {v}")

    # (c) every number has a one-line driver
    if not market.get("driver"):
        violations.append("missing driver")

    # (d) PASS-1 minimum research met
    if not market.get("odds_anchor_fresh") and market.get("research_tier") != "base_rate_fallback":
        violations.append("no fresh (<24h) odds anchor and not base-rate fallback")

    # (e) noisy-register clamp applied if unanchored
    if not market.get("anchored", True):
        p = market.get("p", 50)
        if p < 15 or p > 85:
            violations.append(f"noisy-register market p={p} outside 15–85")

    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------

def handle_409_already_predicted(market: Dict, existing_predictions: List[Dict]) -> Optional[Dict]:
    """
    On 409: find the existing prediction_id for this market and return update call.
    """
    for pred in existing_predictions:
        if pred.get("market_id") == market.get("market_id"):
            return call_update_prediction(pred["id"], market["p"])
    return None


def backoff_429(attempt: int = 1) -> float:
    """Returns sleep duration for 429 backoff (30–60s per D6)."""
    return min(RATE_429_BACKOFF * attempt, 120)


# ---------------------------------------------------------------------------
# Session data fetch (all 4 triage calls)
# ---------------------------------------------------------------------------

def triage_tool_calls() -> List[Dict]:
    """
    Returns the 3 tool calls needed for TRIAGE (§3.1):
    list_matches, list_predictions, list_results.
    Caller executes these; results are passed back for state reconciliation.
    """
    return [
        call_list_matches(),
        call_list_predictions(),
        call_list_results(),
    ]
