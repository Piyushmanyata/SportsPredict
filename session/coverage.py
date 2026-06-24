"""
Coverage state classification and horizon assignment (§2.3, §2.4).

Coverage states:
  UNCOVERED     — no predictions submitted for this match
  PARTIAL       — some open markets unpredicted (top-up immediately)
  COVERED_STALE — predicted but no Depth Pass inside T-24h yet
  COVERED_FRESH — fully predicted + Depth Pass done within last 24h

Horizons:
  NEAR   — < 48h to kickoff  -> Depth Pass mandatory
  MID    — 48h - 7 days      -> PASS-1 recommended
  FAR    — > 7 days          -> PASS-1 if bandwidth allows
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class CoverageState(str, Enum):
    UNCOVERED = "UNCOVERED"
    PARTIAL = "PARTIAL"
    COVERED_STALE = "COVERED-STALE"
    COVERED_FRESH = "COVERED-FRESH"


class Horizon(str, Enum):
    NEAR = "NEAR"       # < 48h
    MID = "MID"         # 48h - 7 days
    FAR = "FAR"         # > 7 days


@dataclass
class MatchStatus:
    match_id: str
    name: str                          # "Team A vs Team B"
    kickoff_utc: datetime
    stage: str                         # "group" | "knockout" | "final"
    coverage: CoverageState
    horizon: Horizon
    hours_to_kickoff: float
    open_markets: int = 0
    predicted_markets: int = 0
    depth_pass_done: bool = False
    depth_pass_time: Optional[datetime] = None
    notes: List[str] = field(default_factory=list)

    @property
    def kickoff_ist(self) -> str:
        """Display kickoff in IST (UTC+5:30) per D8."""
        from datetime import timedelta
        ist = self.kickoff_utc + timedelta(hours=5, minutes=30)
        return ist.strftime("%Y-%m-%d %H:%M IST")

    @property
    def needs_urgent_cover(self) -> bool:
        """UNCOVERED or PARTIAL with < 24h to kickoff."""
        return (self.coverage in (CoverageState.UNCOVERED, CoverageState.PARTIAL)
                and self.hours_to_kickoff < 24)

    @property
    def needs_depth_pass(self) -> bool:
        """Near horizon without a fresh Depth Pass."""
        if self.horizon != Horizon.NEAR:
            return False
        if self.coverage == CoverageState.COVERED_FRESH:
            return not self.depth_pass_done
        return True

    @property
    def is_danger_zone(self) -> bool:
        """True if match could reach kickoff uncovered (< 12h, D1)."""
        return self.hours_to_kickoff < 12 and self.coverage != CoverageState.COVERED_FRESH


def _hours_until(kickoff: datetime) -> float:
    now = datetime.now(timezone.utc)
    delta = kickoff - now
    return delta.total_seconds() / 3600.0


def classify_horizon(hours: float) -> Horizon:
    if hours < 48:
        return Horizon.NEAR
    if hours < 168:  # 7 days
        return Horizon.MID
    return Horizon.FAR


def classify_coverage(
    match_id: str,
    open_markets: int,
    predicted_markets: int,
    depth_pass_done: bool,
    depth_pass_age_hours: Optional[float] = None,
) -> CoverageState:
    """
    Determine coverage state from prediction counts and Depth Pass recency.
    """
    if predicted_markets == 0:
        return CoverageState.UNCOVERED
    if predicted_markets < open_markets:
        return CoverageState.PARTIAL

    # Fully predicted: check Depth Pass freshness
    if not depth_pass_done:
        return CoverageState.COVERED_STALE

    # Depth Pass done: stale if older than 24h
    if depth_pass_age_hours is not None and depth_pass_age_hours > 24:
        return CoverageState.COVERED_STALE

    return CoverageState.COVERED_FRESH


def build_match_status(
    match_data: dict,
    predictions: List[dict],
    depth_passes: Optional[dict] = None,  # match_id -> last depth pass UTC datetime
) -> MatchStatus:
    """
    Build a MatchStatus from API-returned match data and predictions list.

    match_data: dict from list_matches — expects keys:
      id, name/title, opening_time (kickoff UTC ISO str), stage
    predictions: list of prediction dicts from list_predictions
    depth_passes: optional cache of {match_id: datetime} for Depth Pass tracking
    """
    now = datetime.now(timezone.utc)
    kickoff_str = match_data.get("opening_time") or match_data.get("kickoff_time", "")

    try:
        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        kickoff = now  # fallback — flag in notes

    hours = _hours_until(kickoff)
    horizon = classify_horizon(hours)

    # Count predictions for this match
    match_preds = [p for p in predictions
                   if p.get("match_id") == match_data["id"]]

    # Try to figure out open market count from predictions or match data
    open_markets = match_data.get("open_market_count", 10)  # default ~10 per spec
    predicted = len(match_preds)

    # Depth pass tracking
    dp_done = False
    dp_age = None
    if depth_passes and match_data["id"] in depth_passes:
        dp_time = depth_passes[match_data["id"]]
        dp_done = True
        dp_age = (now - dp_time).total_seconds() / 3600.0

    coverage = classify_coverage(
        match_data["id"], open_markets, predicted, dp_done, dp_age
    )

    stage = match_data.get("stage", "group").lower()
    name = match_data.get("name") or match_data.get("title", match_data["id"])

    return MatchStatus(
        match_id=match_data["id"],
        name=name,
        kickoff_utc=kickoff,
        stage=stage,
        coverage=coverage,
        horizon=horizon,
        hours_to_kickoff=max(0.0, hours),
        open_markets=open_markets,
        predicted_markets=predicted,
        depth_pass_done=dp_done,
        depth_pass_time=depth_passes.get(match_data["id"]) if depth_passes else None,
    )


def sort_by_priority(statuses: List[MatchStatus]) -> List[MatchStatus]:
    """
    Sort matches by session priority (§3.4):
    1. UNCOVERED/PARTIAL < 24h (urgent cover)
    2. NEAR horizon with highest Expected RBP opportunity (soonest first as proxy)
    3. NEAR horizon (Depth Pass needed)
    4. MID horizon UNCOVERED/PARTIAL
    5. Everything else
    """
    def priority_key(s: MatchStatus):
        urgent = 0 if s.needs_urgent_cover else 1
        near = 0 if s.horizon == Horizon.NEAR else (1 if s.horizon == Horizon.MID else 2)
        return (urgent, near, s.hours_to_kickoff)

    return sorted(statuses, key=priority_key)
