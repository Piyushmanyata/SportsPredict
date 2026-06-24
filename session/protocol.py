"""
Session protocol skeleton (§3.2) — utility functions used by the autonomous loop.

The actual MCP tool calls happen in the conversational layer (Claude itself).
These helpers format, classify, and structure the information needed per step.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

from .coverage import MatchStatus, CoverageState, Horizon, sort_by_priority


# §3 Session steps
SESSION_STEPS = [
    "SYNC",
    "TRIAGE",
    "SETTLE_AUDIT",
    "DEPTH_PASS",
    "COVERAGE_SWEEP",
    "REPORT",
]


def triage(match_statuses: List[MatchStatus]) -> Dict:
    """
    §3.2 Step 2 — TRIAGE.
    Classify all matches into coverage states and horizons.
    Return a structured triage report.
    """
    near = [s for s in match_statuses if s.horizon == Horizon.NEAR]
    mid = [s for s in match_statuses if s.horizon == Horizon.MID]
    far = [s for s in match_statuses if s.horizon == Horizon.FAR]

    urgent = [s for s in match_statuses if s.needs_urgent_cover]
    danger = [s for s in match_statuses if s.is_danger_zone]
    uncovered = [s for s in match_statuses if s.coverage == CoverageState.UNCOVERED]
    partial = [s for s in match_statuses if s.coverage == CoverageState.PARTIAL]
    stale = [s for s in match_statuses if s.coverage == CoverageState.COVERED_STALE]
    fresh = [s for s in match_statuses if s.coverage == CoverageState.COVERED_FRESH]

    return {
        "total": len(match_statuses),
        "near": near,
        "mid": mid,
        "far": far,
        "urgent_cover": urgent,
        "danger_zone": danger,
        "uncovered": uncovered,
        "partial": partial,
        "stale": stale,
        "fresh": fresh,
        "priority_order": sort_by_priority(match_statuses),
        "flags": _build_triage_flags(danger, urgent, stale),
    }


def _build_triage_flags(danger: list, urgent: list, stale: list) -> List[str]:
    flags = []
    if danger:
        names = [s.name for s in danger]
        flags.append(f"D1 DANGER ZONE (<12h, not FRESH): {', '.join(names)}")
    if urgent:
        names = [s.name for s in urgent]
        flags.append(f"URGENT COVER required (<24h, UNCOVERED/PARTIAL): {', '.join(names)}")
    if stale:
        near_stale = [s for s in stale if s.horizon == Horizon.NEAR]
        if near_stale:
            names = [s.name for s in near_stale]
            flags.append(f"NEAR-HORIZON STALE (Depth Pass overdue): {', '.join(names)}")
    return flags


def format_deadline_table(match_statuses: List[MatchStatus]) -> str:
    """
    Format the deadline table for TRIAGE output (§8.1).
    Shows all matches within 7 days sorted by kickoff.
    """
    within_7d = [s for s in match_statuses if s.hours_to_kickoff <= 168]
    within_7d = sorted(within_7d, key=lambda s: s.hours_to_kickoff)

    lines = ["DEADLINE TABLE (≤7 days, IST):"]
    lines.append(f"{'Match':<30} {'Kickoff (IST)':<22} {'Horizon':<8} {'Coverage':<18} {'Depth Pass'}")
    lines.append("-" * 100)

    for s in within_7d:
        dp_str = "DONE" if s.depth_pass_done else "PENDING"
        lines.append(
            f"{s.name:<30} {s.kickoff_ist:<22} {s.horizon.value:<8} "
            f"{s.coverage.value:<18} {dp_str}"
        )

    return "\n".join(lines)


def format_status_block(
    match_statuses: List[MatchStatus],
    settled_since_last: int,
    session_brier: Optional[float],
    expected_brier: Optional[float],
    actions_taken: str,
    flags: List[str],
    next_checkin: Optional[datetime] = None,
) -> str:
    """
    §8.1 STATUS BLOCK format.
    """
    now_ist = _to_ist(datetime.now(timezone.utc))

    lines = [f"STATUS — {now_ist}"]
    lines.append("")

    # Settled line
    brier_str = ""
    if session_brier is not None and expected_brier is not None:
        brier_str = f" | session Brier {session_brier:.3f} vs self-expected {expected_brier:.3f}"
    lines.append(f"Settled since last: {settled_since_last} markets{brier_str} | cum RBP note: leaderboard lags ≤1h")
    lines.append("")

    # Near horizon
    near = sorted([s for s in match_statuses if s.horizon == Horizon.NEAR],
                  key=lambda s: s.hours_to_kickoff)
    lines.append("Near horizon (<48h, IST):")
    if near:
        for s in near:
            dp = "Y" if s.depth_pass_done else "N"
            lines.append(f"  {s.name} — {s.kickoff_ist} — Depth Pass: {dp} — {s.coverage.value}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Mid/far horizon (≤7d)
    mid_far = sorted(
        [s for s in match_statuses if s.horizon in (Horizon.MID, Horizon.FAR)
         and s.hours_to_kickoff <= 168],
        key=lambda s: s.hours_to_kickoff,
    )
    lines.append("Mid/far horizon (≤7d, IST):")
    if mid_far:
        for s in mid_far:
            lines.append(f"  {s.name} — {s.kickoff_ist} — {s.coverage.value}")
    else:
        lines.append("  (none within 7 days)")
    lines.append("")

    lines.append(f"Actions taken this session: {actions_taken}")
    lines.append("")

    # Flags
    all_flags = flags + [s for s in [_build_coverage_flag(match_statuses)] if s]
    if all_flags:
        lines.append("Flags:")
        for f in all_flags:
            lines.append(f"  • {f}")
    else:
        lines.append("Flags: (none)")
    lines.append("")

    if next_checkin is None:
        next_checkin = datetime.now(timezone.utc) + timedelta(hours=24)
    lines.append(f"NEXT CHECK-IN BY: {_to_ist(next_checkin)} (informational under confirmed daily cadence, §2.4)")

    return "\n".join(lines)


def _build_coverage_flag(statuses: List[MatchStatus]) -> str:
    danger = [s for s in statuses if s.is_danger_zone]
    if danger:
        return f"D1 VIOLATION RISK: {', '.join(s.name for s in danger)} — <12h, not FRESH"
    return ""


def _to_ist(dt: datetime) -> str:
    """Convert UTC datetime to IST string (D8)."""
    ist = dt + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M IST")


def compute_next_checkin(
    match_statuses: List[MatchStatus],
    cadence_confirmed: bool = True,
) -> datetime:
    """
    §2.4 Next check-in computation.
    Under confirmed daily cadence: now + 24h (informational).
    Degraded mode: min(earliest UNCOVERED T-12h, earliest STALE T-3h, now+24h).
    """
    now = datetime.now(timezone.utc)

    if cadence_confirmed:
        return now + timedelta(hours=24)

    # Degraded mode
    candidates = [now + timedelta(hours=24)]

    for s in match_statuses:
        if s.coverage == CoverageState.UNCOVERED:
            candidates.append(s.kickoff_utc - timedelta(hours=12))
        elif s.coverage == CoverageState.COVERED_STALE:
            candidates.append(s.kickoff_utc - timedelta(hours=3))

    return min(candidates)


def should_run_depth_pass(status: MatchStatus) -> bool:
    """True if this match needs a Depth Pass this session."""
    return status.horizon == Horizon.NEAR


def should_run_pass1(status: MatchStatus) -> bool:
    """True if this match needs at least a PASS-1."""
    return status.coverage in (CoverageState.UNCOVERED, CoverageState.PARTIAL)


def matchday3_protocol(match_pair: Tuple[MatchStatus, MatchStatus]) -> str:
    """
    §3.3 Matchday-3 simultaneous kickoff pair handling.
    Returns research guidance for the pair.
    """
    m1, m2 = match_pair
    lines = [
        f"MATCHDAY-3 PAIR: {m1.name} | {m2.name}",
        "  1. Qualification scenarios first ('what does each side need?')",
        "  2. Rotation risk: already-qualified sides -> -3-6 on favourite win; slash player props",
        "  3. Correlated basket spans BOTH matches: widen L8 check accordingly",
        "  4. Player props: enter conservatively (low end of bands); let lineups do the work",
    ]
    return "\n".join(lines)
