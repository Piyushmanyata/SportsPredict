"""Session-protocol helpers: IST time, horizons, coverage state, STATUS BLOCK (spec D7/D8, 2.3, 2.4, 4.2, 8.1).

The live API returns match "opening_time" (kickoff) and "closing_time"
(kickoff + 2:30, a settlement window) as ISO-8601 UTC strings. Per D7 the
hard lock is whichever of the two is EARLIER -- in practice that is
always opening_time, but hard_lock() takes an explicit min() rather than
assuming that ordering.
"""

import datetime

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def parse_iso_utc(s):
    """Parse an ISO-8601 UTC timestamp like '2026-06-11T19:00:00Z' into an aware datetime."""
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def to_ist(dt_utc):
    """Convert an aware UTC datetime to IST (UTC+5:30)."""
    return dt_utc.astimezone(IST)


def format_ist(dt_utc):
    """Render a UTC datetime as an IST-labeled string, e.g. '2026-06-12 00:30 IST'."""
    return to_ist(dt_utc).strftime("%Y-%m-%d %H:%M IST")


def hard_lock(opening_time_utc, closing_time_utc=None):
    """The effective submission deadline: the earlier of opening_time and closing_time."""
    if closing_time_utc is None:
        return opening_time_utc
    return min(opening_time_utc, closing_time_utc)


def horizon_tier(now_utc, opening_time_utc):
    """Classify a match into 'past' / 'near' (<48h) / 'mid' (<7d) / 'far' horizons."""
    hours_to_kickoff = (opening_time_utc - now_utc).total_seconds() / 3600.0
    if hours_to_kickoff < 0:
        return "past"
    if hours_to_kickoff < 48:
        return "near"
    if hours_to_kickoff < 168:
        return "mid"
    return "far"


def coverage_state(any_predictions, any_open_unpredicted, hours_since_last_depth_pass):
    """Classify a match's coverage state per the D1 zero-miss doctrine."""
    if not any_predictions:
        return "UNCOVERED"
    if any_open_unpredicted:
        return "PARTIAL"
    if hours_since_last_depth_pass is None or hours_since_last_depth_pass > 24:
        return "COVERED-STALE"
    return "COVERED-FRESH"


def next_checkin_by(now_utc, default_hours=24.0):
    """Informational next-check-in timestamp under confirmed daily cadence."""
    return now_utc + datetime.timedelta(hours=default_hours)


def degraded_mode_deadline(now_utc, earliest_uncovered_kickoff=None, earliest_stale_kickoff=None):
    """Degraded-mode fallback deadline per section 2.4 when daily cadence has slipped."""
    candidates = [now_utc + datetime.timedelta(hours=24)]
    if earliest_uncovered_kickoff is not None:
        candidates.append(earliest_uncovered_kickoff - datetime.timedelta(hours=12))
    if earliest_stale_kickoff is not None:
        candidates.append(earliest_stale_kickoff - datetime.timedelta(hours=3))
    return min(candidates)


def format_status_block(now_utc, settled_since_last, session_brier, self_expected_brier,
                         near_horizon, mid_far_horizon, actions_taken, flags, next_checkin_utc):
    """Build the section 8.1 STATUS BLOCK text."""
    header_date = to_ist(now_utc).strftime("%Y-%m-%d")
    near_lines = "\n".join(near_horizon) if near_horizon else "(none)"
    mid_far_lines = "\n".join(mid_far_horizon) if mid_far_horizon else "(none)"
    return (
        f"STATUS -- {header_date}\n"
        f"Settled since last: {settled_since_last} markets | "
        f"session Brier {session_brier:.4f} vs self-expected {self_expected_brier:.4f}\n"
        f"Near horizon (<48h, IST):\n{near_lines}\n"
        f"Mid/far horizon (<=7d, IST):\n{mid_far_lines}\n"
        f"Actions taken this session: {actions_taken}\n"
        f"Flags: {flags}\n"
        f"NEXT CHECK-IN BY: {format_ist(next_checkin_utc)}"
    )


if __name__ == "__main__":
    ist_dt = to_ist(parse_iso_utc("2026-06-11T19:00:00Z"))
    assert (ist_dt.month, ist_dt.day, ist_dt.hour, ist_dt.minute) == (6, 12, 0, 30)
    ist_dt = to_ist(parse_iso_utc("2026-06-11T02:00:00Z"))
    assert (ist_dt.month, ist_dt.day, ist_dt.hour, ist_dt.minute) == (6, 11, 7, 30)
    print("check 1 (D8 IST conversion examples) OK")

    now = parse_iso_utc("2026-06-20T00:00:00Z")
    assert horizon_tier(now, parse_iso_utc("2026-06-21T06:00:00Z")) == "near"
    assert horizon_tier(now, parse_iso_utc("2026-06-24T00:00:00Z")) == "mid"
    assert horizon_tier(now, parse_iso_utc("2026-07-01T00:00:00Z")) == "far"
    assert horizon_tier(now, parse_iso_utc("2026-06-19T00:00:00Z")) == "past"
    print("check 2 (horizon tiers) OK")

    assert coverage_state(False, False, None) == "UNCOVERED"
    assert coverage_state(True, True, None) == "PARTIAL"
    assert coverage_state(True, False, 30) == "COVERED-STALE"
    assert coverage_state(True, False, 5) == "COVERED-FRESH"
    print("check 3 (coverage states) OK")

    opening = parse_iso_utc("2026-06-11T19:00:00Z")
    closing = parse_iso_utc("2026-06-11T21:30:00Z")
    assert hard_lock(opening, closing) == opening
    assert hard_lock(closing, opening) == opening  # earlier value governs regardless of arg order
    print("check 4 (hard lock takes the earlier timestamp) OK")

    now = parse_iso_utc("2026-06-20T00:00:00Z")
    uncovered = parse_iso_utc("2026-06-20T10:00:00Z")
    deadline = degraded_mode_deadline(now, earliest_uncovered_kickoff=uncovered)
    assert deadline == parse_iso_utc("2026-06-19T22:00:00Z")
    print("check 5 (degraded-mode deadline) OK")

    block = format_status_block(
        now_utc=now, settled_since_last=5, session_brier=0.21, self_expected_brier=0.20,
        near_horizon=["MEX vs RSA -- 2026-06-21 -- Depth Pass done? Y"],
        mid_far_horizon=["BRA vs MAR -- 2026-06-25 -- COVERED-FRESH"],
        actions_taken="Depth Pass: 1 match / 10 markets", flags="none",
        next_checkin_utc=next_checkin_by(now),
    )
    assert "NEXT CHECK-IN BY" in block and "STATUS --" in block
    print("check 6 (status block renders) OK")

    print("session.py: all checks passed")
