"""
Session triage (§3.1 / §3.2 Step 2).

Classifies matches into coverage states and horizon tiers.
Prints the deadline table in IST.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass
from constants import (
    UNCOVERED, PARTIAL, COVERED_STALE, COVERED_FRESH, IST_OFFSET_HOURS
)

IST = timezone(timedelta(hours=IST_OFFSET_HOURS))


class Horizon(str, Enum):
    NEAR  = "near"    # < 48h
    MID   = "mid"     # 48h – 7d
    FAR   = "far"     # > 7d


@dataclass
class MatchTriage:
    match_id:    str
    name:        str          # "Team A vs Team B"
    kickoff_utc: datetime     # UTC-aware
    state:       str          # UNCOVERED / PARTIAL / COVERED-STALE / COVERED-FRESH
    horizon:     Horizon
    n_markets:   int = 0
    n_predicted: int = 0
    depth_pass_done: bool = False

    @property
    def kickoff_ist(self) -> datetime:
        return self.kickoff_utc.astimezone(IST)

    @property
    def hours_to_kick(self) -> float:
        now = datetime.now(timezone.utc)
        delta = self.kickoff_utc - now
        return delta.total_seconds() / 3600

    @property
    def is_urgent(self) -> bool:
        """Match is <24h away and not COVERED-FRESH."""
        return self.hours_to_kick < 24 and self.state != COVERED_FRESH

    @property
    def needs_depth_pass(self) -> bool:
        """All near-horizon matches need a Depth Pass (§2.3)."""
        return self.horizon == Horizon.NEAR and not self.depth_pass_done


def _hours_to_kick(kickoff_utc: datetime) -> float:
    now = datetime.now(timezone.utc)
    return max(0.0, (kickoff_utc - now).total_seconds() / 3600)


def classify_horizon(kickoff_utc: datetime) -> Horizon:
    h = _hours_to_kick(kickoff_utc)
    if h < 48:
        return Horizon.NEAR
    if h <= 168:
        return Horizon.MID
    return Horizon.FAR


def classify_state(
    match_id: str,
    n_markets: int,
    n_predicted: int,
    last_depth_pass_utc: datetime | None,
    kickoff_utc: datetime,
) -> str:
    """
    Classify a match into one of four coverage states (§2.4).

    last_depth_pass_utc: when the most recent Depth Pass was submitted, or None.
    """
    if n_predicted == 0:
        return UNCOVERED
    if n_predicted < n_markets:
        return PARTIAL

    # Has predictions for all open markets — check freshness
    if last_depth_pass_utc is None:
        return COVERED_STALE

    now = datetime.now(timezone.utc)
    age_hours = (now - last_depth_pass_utc).total_seconds() / 3600
    hours_to_kick = _hours_to_kick(kickoff_utc)

    # Stale if no Depth Pass within T−24h (§2.4)
    if hours_to_kick < 24 and age_hours > 24:
        return COVERED_STALE

    return COVERED_FRESH


def classify_matches(
    matches: list[dict],
    predictions: list[dict],
    depth_pass_log: dict[str, datetime] | None = None,
) -> list[MatchTriage]:
    """
    Main triage function. Takes raw API responses and returns MatchTriage list.

    Parameters
    ----------
    matches : list[dict]
        From list_matches() API response.
    predictions : list[dict]
        From list_predictions() API response.
    depth_pass_log : dict[match_id → last_depth_pass_utc] or None
        In-session record of when Depth Passes ran.

    Returns
    -------
    list[MatchTriage], sorted by kickoff_utc ascending.
    """
    if depth_pass_log is None:
        depth_pass_log = {}

    # Index predictions by match_id
    pred_by_match: dict[str, int] = {}
    for p in predictions:
        mid = p.get("match_id") or p.get("matchId", "")
        pred_by_match[mid] = pred_by_match.get(mid, 0) + 1

    result = []
    for m in matches:
        mid      = m.get("id") or m.get("matchId", "")
        name     = m.get("name") or f"{m.get('home','?')} vs {m.get('away','?')}"
        kick_str = m.get("opening_time") or m.get("openingTime", "")
        try:
            kick_utc = datetime.fromisoformat(kick_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Skip already-settled matches (closing_time in the past by >2h)
        hours_to_kick = _hours_to_kick(kick_utc)
        if hours_to_kick < -3:
            continue

        n_markets   = m.get("market_count") or m.get("marketCount", 10)
        n_predicted = pred_by_match.get(mid, 0)
        last_dp     = depth_pass_log.get(mid)
        horizon     = classify_horizon(kick_utc)
        state       = classify_state(mid, n_markets, n_predicted, last_dp, kick_utc)

        result.append(MatchTriage(
            match_id    = mid,
            name        = name,
            kickoff_utc = kick_utc,
            state       = state,
            horizon     = horizon,
            n_markets   = n_markets,
            n_predicted = n_predicted,
            depth_pass_done = last_dp is not None,
        ))

    result.sort(key=lambda x: x.kickoff_utc)
    return result


def print_deadline_table(triaged: list[MatchTriage]) -> str:
    """Format the deadline table for the STATUS BLOCK (§8.1)."""
    lines = []
    lines.append(f"{'Match':<30} {'Kickoff (IST)':<22} {'Horizon':<8} {'State':<18} {'Mkt':>4} {'Pred':>4}")
    lines.append("-" * 95)
    for t in triaged:
        kick_ist = t.kickoff_ist.strftime("%d %b %H:%M IST")
        flag = " ⚠" if t.is_urgent else ("  ⏰" if t.needs_depth_pass else "")
        lines.append(
            f"{t.name:<30} {kick_ist:<22} {t.horizon.value:<8} {t.state:<18} "
            f"{t.n_markets:>4} {t.n_predicted:>4}{flag}"
        )
    return "\n".join(lines)
