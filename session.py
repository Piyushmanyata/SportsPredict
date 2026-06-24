"""
Session Protocol Runner — Jump Trading Probability Cup
Implements §3 (session protocol) of the system instructions (v8-final).

Usage:
    from session import STATUS_BLOCK, triage, coverage_state
    from engine import derive_all_markets, to_int_calibrated, EVENT_ID, LOBBY_ID
"""

import math
from datetime import datetime, timezone, timedelta
from engine import (
    EVENT_ID, LOBBY_ID, WEIGHT_GROUP, WEIGHT_KNOCKOUT, WEIGHT_FINAL,
    brier, rbp, noise_band_1sigma, decode_outcome, to_int_calibrated
)

# IST = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))


# ── Time helpers ─────────────────────────────────────────────────────────────

def utc_to_ist(utc_dt):
    """Convert UTC datetime to IST (UTC+5:30)."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(IST)

def parse_iso(s):
    """Parse ISO 8601 string to datetime."""
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)

def hours_to_kickoff(opening_time_str, now_utc=None):
    """Hours remaining until kickoff (negative = past kickoff)."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    kickoff = parse_iso(opening_time_str)
    delta = kickoff - now_utc
    return delta.total_seconds() / 3600

def ist_label(opening_time_str):
    """Human-readable IST kickoff label, e.g. '25-Jun 00:30 IST'."""
    dt = utc_to_ist(parse_iso(opening_time_str))
    return dt.strftime("%d-%b %H:%M IST")


# ── Match classification (§3.1 Tier Priority) ────────────────────────────────

TIER_EMERGENCY = "T1-EMERGENCY"   # uncovered AND < 12h to kickoff (D1 breach risk)
TIER_URGENT    = "T2-URGENT"      # uncovered AND < 24h
TIER_DEPTH     = "T3a-DEPTH"      # covered AND < 48h → needs Depth Pass
TIER_COVERAGE  = "T3b-COVERAGE"   # uncovered/partial AND > 24h → Coverage Sweep
TIER_OK        = "T4-OK"          # covered AND > 48h

def classify_match(match, covered_market_ids, now_utc=None):
    """
    Classify a match into a tier based on coverage state and time to kickoff.
    match: dict from list_matches API (id, name, opening_time, open_market_count)
    covered_market_ids: set of market_ids that already have predictions
    Returns: (tier, hours_remaining, ist_label)
    """
    h = hours_to_kickoff(match["opening_time"], now_utc)
    ist = ist_label(match["opening_time"])

    # Coverage: we can't easily check per-match here without the market IDs,
    # so callers should pass whether match is covered.
    return h, ist

def triage(matches, prediction_market_ids, now_utc=None):
    """
    TRIAGE step (§3, Tier 1): classify all matches by coverage and horizon.
    matches: list of match dicts from list_matches
    prediction_market_ids: set of market_ids that already have predictions
    Returns list of (tier, match, hours_left, ist_str) sorted by urgency.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    rows = []
    for m in matches:
        h    = hours_to_kickoff(m["opening_time"], now_utc)
        ist  = ist_label(m["opening_time"])
        mid  = m["id"]
        # We determine coverage by whether the match's markets appear in predictions.
        # This requires a mapping built during SYNC (see build_coverage_map below).
        rows.append((h, ist, m))

    rows.sort(key=lambda x: x[0])  # ascending hours = most urgent first
    return rows

def build_coverage_map(predictions, markets_by_match):
    """
    Build a dict: match_id → coverage_fraction (0 = uncovered, 1 = fully covered).
    predictions: list of prediction dicts (from list_predictions)
    markets_by_match: dict of match_id → list of market dicts
    """
    predicted_market_ids = {p["market_id"] for p in predictions}
    coverage = {}
    for match_id, markets in markets_by_match.items():
        total   = len(markets)
        covered = sum(1 for m in markets if m["id"] in predicted_market_ids)
        coverage[match_id] = covered / total if total > 0 else 0.0
    return coverage


# ── Settle Audit (§3, §9) ────────────────────────────────────────────────────

def settle_audit(results):
    """
    Decode outcomes and compute calibration stats from list_results.
    results: list of result dicts with probability_submitted and brier_score.
    Returns calibration summary dict.
    """
    n      = 0
    sum_b  = 0.0
    sum_eb = 0.0
    decoded = []

    for r in results:
        bs = r.get("brier_score")
        if bs is None:
            continue
        p_int = r.get("probability_submitted") or r.get("probability")
        if p_int is None:
            continue
        p   = p_int / 100.0
        n  += 1
        sum_b  += bs
        sum_eb += p * (1 - p)
        outcome = decode_outcome(p_int, bs)
        decoded.append({"market_id": r.get("market_id"), "p": p, "brier": bs, "outcome": outcome})

    if n == 0:
        return {"n": 0}

    mean_b  = sum_b / n
    mean_eb = sum_eb / n
    gap     = mean_b - mean_eb
    sigma   = noise_band_1sigma(n)
    gap_sigma = gap / sigma if sigma > 0 else 0

    if gap_sigma < 0.7:
        calibration_status = "GREEN ✓"
    elif gap_sigma < 1.5:
        calibration_status = "AMBER"
    else:
        calibration_status = "RED ⚠"

    return {
        "n":             n,
        "mean_brier":    round(mean_b, 4),
        "self_expected": round(mean_eb, 4),
        "gap":           round(gap, 4),
        "gap_sigma":     round(gap_sigma, 2),
        "status":        calibration_status,
        "decoded":       decoded,
    }


# ── STATUS BLOCK (§8.1) ──────────────────────────────────────────────────────

def format_status_block(matches, results, predictions, session_actions=None):
    """
    Generate the mandatory STATUS BLOCK (§8.1).
    matches: list from list_matches
    results: list from list_results
    predictions: list from list_predictions
    session_actions: dict of {depth_pass_n, coverage_sweep_n, topups_n}
    """
    now_ist   = datetime.now(IST)
    date_str  = now_ist.strftime("%Y-%m-%d %H:%M IST")
    audit     = settle_audit(results)

    # Predicted market ID set
    pred_market_ids = {p.get("market_id") for p in predictions}

    now_utc = datetime.now(timezone.utc)
    near    = []  # < 48h
    midfar  = []  # >= 48h

    for m in sorted(matches, key=lambda x: x["opening_time"]):
        h   = hours_to_kickoff(m["opening_time"], now_utc)
        ist = ist_label(m["opening_time"])
        if h < 48:
            near.append((m["name"], ist, h))
        else:
            midfar.append((m["name"], ist, h))

    lines = [
        f"STATUS — {date_str}",
        f"Settled: {audit.get('n', '?')} mkts | Brier {audit.get('mean_brier','?')} vs expected {audit.get('self_expected','?')} | Gap {audit.get('gap','?')} ({audit.get('gap_sigma','?')}σ) {audit.get('status','')}",
        "",
        "Near horizon (<48h, IST):",
    ]
    for name, ist, h in near:
        lines.append(f"  {name} — {ist} — {h:.1f}h to kickoff")

    lines.append("\nMid/far horizon (≥48h, IST):")
    for name, ist, h in midfar[:10]:  # cap display
        lines.append(f"  {name} — {ist}")

    if session_actions:
        lines.append(
            f"\nActions: Depth Pass {session_actions.get('depth_pass_n',0)} mkts · "
            f"Coverage sweep {session_actions.get('coverage_sweep_n',0)} mkts · "
            f"Top-ups {session_actions.get('topups_n',0)}"
        )

    # Next check-in: 6 hours from now for standard sessions
    next_checkin = now_ist + timedelta(hours=6)
    lines.append(f"\nNEXT CHECK-IN BY: {next_checkin.strftime('%Y-%m-%d %H:%M IST')}")
    return "\n".join(lines)


# ── After-Action Report (§8.2) ───────────────────────────────────────────────

def format_after_action_report(submissions, match_name, batch_result=None):
    """
    Generate mandatory after-action report for autonomous writes (§8.2).
    submissions: list of {market_q, mode, p, conf, driver}
    batch_result: API response from submit_predictions_batch
    """
    lines = [f"\n# AFTER-ACTION REPORT — {match_name}"]
    lines.append(f"{'#':<3} {'Market':<55} {'Mode':<10} {'p':>4} {'Conf':<6} Driver")
    lines.append("-" * 100)
    for i, s in enumerate(submissions, 1):
        q = s.get("market_q", "")[:54]
        lines.append(
            f"{i:<3} {q:<55} {s.get('mode','ANCHORED'):<10} {s.get('p','?'):>4} "
            f"{s.get('conf','MED'):<6} {s.get('driver','—')}"
        )
    if batch_result:
        ok  = batch_result.get("succeeded", 0)
        bad = batch_result.get("failed", 0)
        lines.append(f"\nBatch: {ok} succeeded / {bad} failed")
        for r in batch_result.get("results", []):
            if not r.get("success"):
                lines.append(f"  FAIL {r['market_id'][:8]}… {r.get('error','')}")
    return "\n".join(lines)


# ── Batch submission helper ──────────────────────────────────────────────────

def make_prediction(market_id, p_float, avoid_50=True):
    """Build a single prediction dict for submit_predictions_batch."""
    return {
        "market_id": market_id,
        "lobby_id":  LOBBY_ID,
        "probability": to_int_calibrated(p_float, avoid_50=avoid_50),
    }

def chunk_predictions(predictions, size=50):
    """Split prediction list into chunks of ≤50 for API rate limits (D6)."""
    for i in range(0, len(predictions), size):
        yield predictions[i:i + size]


# ── RBP Opportunity Pass (§2.5 / §6.5) ──────────────────────────────────────

def rbp_opportunity_label(p_yours, p_crowd, p_true_est=None):
    """
    Classify the RBP edge opportunity for a market (§2.5).
    p_crowd: crowd's submitted probability (0-1)
    p_yours: your submitted probability (0-1)
    Returns: label ∈ {STRONG, MODERATE, THIN, NONE}
    """
    if p_crowd is None:
        return "THIN"
    deviation = abs(p_yours - p_crowd)
    if deviation >= 0.12:
        return "STRONG"
    if deviation >= 0.06:
        return "MODERATE"
    if deviation >= 0.02:
        return "THIN"
    return "NONE"


# ── Lesson Lifecycle (§9.4) ──────────────────────────────────────────────────

LESSON_THRESHOLDS = {
    "PROVISIONAL":  {"n_min": 1,  "next": "ACTIVE"},
    "ACTIVE":       {"n_min": 8,  "next": "CONFIRMED"},
    "CONFIRMED":    {"n_min": 20, "next": "RETIRED"},
    "RETIRED":      {"n_min": 999, "next": None},
}

def check_lesson_graduation(lesson):
    """
    Check if a lesson should graduate to the next lifecycle stage (§9.4 / D11).
    lesson: dict with {status, n, directional_consistency (bool)}
    Returns suggested new status or None if no change.
    """
    status = lesson.get("status", "PROVISIONAL")
    n      = lesson.get("n", 0)
    consistent = lesson.get("directional_consistency", False)

    thresholds = LESSON_THRESHOLDS.get(status, {})
    n_min = thresholds.get("n_min", 999)
    next_s = thresholds.get("next")

    if next_s and n >= n_min and consistent:
        return next_s
    return None


# ── Quick sanity ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    now_ist = datetime.now(IST)
    print(f"Current IST: {now_ist.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"Event ID:    {EVENT_ID}")
    print(f"Lobby ID:    {LOBBY_ID}")
