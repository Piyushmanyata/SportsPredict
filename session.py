"""
Session protocol utilities — §3 of the system instructions (v8-final).
Covers TRIAGE, horizon classification, coverage states, IST conversion.
"""

from datetime import datetime, timezone, timedelta
import json

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------

def now_utc():
    return datetime.now(UTC)

def to_ist(dt):
    """Convert any aware datetime to IST."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)

def parse_iso(s):
    """Parse ISO 8601 UTC string → aware datetime."""
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)

def hours_to_kickoff(opening_time_str):
    """Hours from now until kickoff."""
    kickoff = parse_iso(opening_time_str)
    delta = kickoff - now_utc()
    return delta.total_seconds() / 3600.0

def fmt_ist(dt):
    """Format datetime as IST string for reports."""
    return to_ist(dt).strftime("%Y-%m-%d %H:%M IST")

# ---------------------------------------------------------------------------
# §2.3  Horizon classification
# ---------------------------------------------------------------------------

HORIZON_NEAR = 48    # hours — Depth Pass mandatory
HORIZON_MID  = 168   # hours (7 days) — PASS-1 mandatory
# > 7 days = far horizon — opportunistic PASS-1

def classify_horizon(opening_time_str):
    h = hours_to_kickoff(opening_time_str)
    if h < 0:
        return "PAST"
    elif h < HORIZON_NEAR:
        return "NEAR"
    elif h < HORIZON_MID:
        return "MID"
    else:
        return "FAR"

# ---------------------------------------------------------------------------
# §2.4  Coverage states
# ---------------------------------------------------------------------------

def classify_coverage(match_id, predictions, markets_count):
    """
    Given a set of predictions (list of dicts with market_id), and the
    number of open markets for this match, return coverage state.
    UNCOVERED: 0 predictions for this match.
    PARTIAL: some but not all markets predicted.
    COVERED-STALE: all predicted but no Depth Pass in last 24h (approximated).
    COVERED-FRESH: all predicted + Depth Pass done (session tracking).
    """
    pred_ids = {p.get("market_id") for p in predictions}
    # We can't know which market IDs belong to this match without fetching them,
    # so use a simple heuristic: count predictions associated with this match.
    # Caller should pass the correct subset.
    n = len(pred_ids)
    if n == 0:
        return "UNCOVERED"
    elif n < markets_count:
        return "PARTIAL"
    else:
        return "COVERED-STALE"  # assume stale until Depth Pass confirmed

# ---------------------------------------------------------------------------
# §3  Session loop helper
# ---------------------------------------------------------------------------

def triage_table(matches, predictions_by_match_id):
    """
    Build deadline table for STATUS BLOCK.
    matches: list from list_matches API.
    predictions_by_match_id: dict(match_id → count of predicted markets).
    """
    rows = []
    for m in matches:
        h = hours_to_kickoff(m["opening_time"])
        horizon = classify_horizon(m["opening_time"])
        n_pred = predictions_by_match_id.get(m["id"], 0)
        n_open = m.get("open_market_count", 10)
        if n_pred == 0:
            state = "UNCOVERED"
        elif n_pred < n_open:
            state = "PARTIAL"
        else:
            state = "COVERED-STALE"
        rows.append({
            "name": m["name"],
            "kickoff_ist": fmt_ist(parse_iso(m["opening_time"])),
            "hours_to_ko": round(h, 1),
            "horizon": horizon,
            "state": state,
            "n_pred": n_pred,
            "n_open": n_open,
        })
    rows.sort(key=lambda r: r["hours_to_ko"])
    return rows

# ---------------------------------------------------------------------------
# §8.1  STATUS BLOCK printer
# ---------------------------------------------------------------------------

def print_status_block(triage_rows, session_date_ist=None, flags=None):
    """Print the STATUS BLOCK per §8.1 format."""
    if session_date_ist is None:
        session_date_ist = fmt_ist(now_utc())
    lines = [f"\n{'='*60}", f"STATUS — {session_date_ist}"]
    lines.append("-" * 60)
    lines.append(f"{'Match':<20} {'Kickoff (IST)':<22} {'Horizon':<8} {'State':<16} {'Covered'}")
    lines.append("-" * 60)
    for r in triage_rows:
        covered = f"{r['n_pred']}/{r['n_open']}"
        lines.append(
            f"{r['name']:<20} {r['kickoff_ist']:<22} {r['horizon']:<8} {r['state']:<16} {covered}"
        )
    if flags:
        lines.append("\nFlags: " + "; ".join(flags))
    next_checkin = fmt_ist(now_utc() + timedelta(hours=24))
    lines.append(f"\nNEXT CHECK-IN BY: {next_checkin}  (informational — daily cadence confirmed)")
    lines.append("=" * 60)
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# §8.2  After-action report builder
# ---------------------------------------------------------------------------

def build_report_row(market_q, mode, p_int, conf, driver):
    """One row for the after-action prediction table."""
    return {
        "question": market_q[:60],
        "mode": mode,
        "p": p_int,
        "conf": conf,
        "driver": driver[:80],
    }

def print_report_table(match_name, kickoff_ist, rows):
    header = f"\n--- {match_name} | Kickoff: {kickoff_ist} ---"
    col_h  = f"{'#':<3} {'Market':<45} {'Mode':<10} {'p':>4} {'Conf':<8} Driver"
    divider = "-" * 120
    lines  = [header, col_h, divider]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i:<3} {r['question']:<45} {r['mode']:<10} {r['p']:>4} {r['conf']:<8} {r['driver']}"
        )
    return "\n".join(lines)
