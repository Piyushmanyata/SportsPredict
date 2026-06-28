"""
Utility helpers: IST time, outcome decoding, base-rate fallback.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def utc_to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def parse_iso(s: str) -> datetime:
    """Parse ISO-8601 string to aware UTC datetime."""
    s = s.rstrip("Z")
    if "+" in s[10:] or "-" in s[10:]:
        return datetime.fromisoformat(s)
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def format_ist(dt: datetime) -> str:
    """Return 'YYYY-MM-DD HH:MM IST'."""
    ist_dt = utc_to_ist(dt)
    return ist_dt.strftime("%Y-%m-%d %H:%M IST")


def seconds_to_kickoff(opening_time_str: str) -> float:
    """Positive = future, negative = past."""
    kickoff = parse_iso(opening_time_str)
    return (kickoff - datetime.now(tz=timezone.utc)).total_seconds()


def horizon_label(opening_time_str: str) -> str:
    """Returns 'near', 'mid', or 'far'."""
    secs = seconds_to_kickoff(opening_time_str)
    if secs < 0:
        return "past"
    if secs <= 48 * 3600:
        return "near"
    if secs <= 7 * 24 * 3600:
        return "mid"
    return "far"


def decode_outcome_from_brier(p_submitted: int, brier: float) -> Optional[int]:
    """
    §9.2 outcome decode: Brier = (p - o)^2 where p in [0,1], o in {0,1}.
    Returns 1 (TRUE) or 0 (FALSE) or None if ambiguous.
    Avoid submitting exactly 50 (D3) so this stays unambiguous.
    """
    p = p_submitted / 100.0
    err_if_true  = (p - 1.0) ** 2
    err_if_false = (p - 0.0) ** 2
    tol = 1e-4
    if abs(brier - err_if_true) < tol:
        return 1
    if abs(brier - err_if_false) < tol:
        return 0
    return None


def clamp(value: float, lo: float = 1.0, hi: float = 99.0) -> int:
    """Round and clamp to integer in [lo, hi], never return 50 if avoidable."""
    v = int(round(max(lo, min(hi, value))))
    if v == 50:
        return 51  # D3: avoid exact 50
    return v


def noisy_register_clamp(p: float, anchored: bool = False) -> int:
    """§5.9: clamp unanchored noisy-register markets to 15–85."""
    from bot.config import NOISY_REGISTER_LOW, NOISY_REGISTER_HIGH
    if not anchored:
        p = max(NOISY_REGISTER_LOW, min(NOISY_REGISTER_HIGH, p))
    return clamp(p)
