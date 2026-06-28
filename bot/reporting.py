"""
Reporting formats: STATUS BLOCK, After-Action Report, RBP Scoreboard.
All times in IST (D8). All report functions return strings.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from bot.utils import now_ist, format_ist, decode_outcome_from_brier, seconds_to_kickoff, horizon_label


# ---------------------------------------------------------------------------
# STATUS BLOCK (§8.1) — emitted at start of every session
# ---------------------------------------------------------------------------

def status_block(
    matches: List[Dict],
    predictions: List[Dict],
    results: List[Dict],
    coverage_tracker,        # CoverageTracker instance
    session_brier: Optional[float] = None,
    self_expected_brier: Optional[float] = None,
    cum_rbp: Optional[float] = None,
    next_checkin_ist: Optional[str] = None,
    flags: Optional[List[str]] = None,
    actions_depth: int = 0,
    actions_markets_depth: int = 0,
    actions_sweep: int = 0,
    actions_markets_sweep: int = 0,
) -> str:
    now = now_ist().strftime("%Y-%m-%d %H:%M IST")
    settled_since = len([r for r in results if r.get("brier_score") is not None])

    lines = [
        f"STATUS — {now}",
        f"Settled since last: {settled_since} markets"
        + (f" | session Brier {session_brier:.4f} vs expected {self_expected_brier:.4f}" if session_brier else "")
        + (f" | cum RBP {cum_rbp:+.1f} (lags ≤1h)" if cum_rbp is not None else ""),
        "",
    ]

    # Near horizon (<48h)
    near = [m for m in coverage_tracker.all_matches()
            if horizon_label(m["opening_time"]) == "near"]
    if near:
        lines.append("Near horizon (<48h):")
        for m in sorted(near, key=lambda x: x["opening_time"]):
            dp = "Y" if m["coverage"] == "COVERED-FRESH" else "N"
            kickoff = format_ist(__import__("bot.utils", fromlist=["parse_iso"]).parse_iso(m["opening_time"]))
            lines.append(f"  {m['name']} — {kickoff} — Depth Pass: {dp} — {m['coverage']}")
    else:
        lines.append("Near horizon (<48h): none")

    lines.append("")

    # Mid/far (≤7d)
    mid = [m for m in coverage_tracker.all_matches()
           if horizon_label(m["opening_time"]) in ("mid", "far")]
    if mid:
        lines.append("Mid/far (≤7d):")
        for m in sorted(mid, key=lambda x: x["opening_time"])[:10]:
            kickoff = format_ist(__import__("bot.utils", fromlist=["parse_iso"]).parse_iso(m["opening_time"]))
            lines.append(f"  {m['name']} — {kickoff} — {m['coverage']} ({m['n_covered']}/{m['n_markets']})")
    else:
        lines.append("Mid/far (≤7d): none")

    lines.append("")

    # Actions
    lines.append(
        f"Actions: Depth Pass: {actions_depth} matches / {actions_markets_depth} markets"
        f" · Coverage sweep: {actions_sweep} matches / {actions_markets_sweep} markets"
    )

    # Flags
    if flags:
        lines.append(f"Flags: {' | '.join(flags)}")

    if next_checkin_ist:
        lines.append(f"NEXT CHECK-IN BY: {next_checkin_ist}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AFTER-ACTION REPORT (§8.2)
# ---------------------------------------------------------------------------

def after_action_report(
    match: Dict,
    submitted_markets: List[Dict],
    batch_results: Optional[List[Dict]] = None,
    opportunity_pass: Optional[Dict] = None,
    stage: str = "group",
) -> str:
    from bot.config import STAGE_WEIGHTS

    weight = STAGE_WEIGHTS.get(stage, 1.0)
    kickoff = format_ist(__import__("bot.utils", fromlist=["parse_iso"]).parse_iso(match.get("opening_time", "")))
    horizon = horizon_label(match.get("opening_time", ""))
    secs = seconds_to_kickoff(match.get("opening_time", ""))

    header = (
        f"\n{'='*60}\n"
        f"MATCH: {match.get('name', match.get('id','?'))}\n"
        f"Kickoff (IST): {kickoff} | Stage weight: {weight}× | Horizon: {horizon} | "
        f"T−{abs(secs)/3600:.1f}h | Mode: FULL AUTONOMY\n"
        f"{'='*60}"
    )

    # Market table
    rows = [f"{'#':<3} {'Market':<45} {'Mode':<10} {'p':>4} {'Conf':<8} Driver"]
    rows.append("-" * 90)
    for i, m in enumerate(submitted_markets, 1):
        rows.append(
            f"{i:<3} {m.get('question','')[:45]:<45} "
            f"{m.get('mode','MODELED'):<10} "
            f"{m.get('p', '?'):>4} "
            f"{m.get('confidence','MED'):<8} "
            f"{m.get('driver','')[:40]}"
        )

    # Biggest edges
    edges = _summarise_edges(submitted_markets)

    # Batch confirmation
    if batch_results:
        successes = sum(1 for r in batch_results if r.get("success"))
        failures  = [r for r in batch_results if not r.get("success")]
        batch_line = (
            f"\nBatch: {successes}/{len(batch_results)} succeeded"
            + (f" | Failures: {[f.get('market_id','?') for f in failures]}" if failures else "")
        )
    else:
        batch_line = "\nBatch: pending"

    # Watchlist
    watchlist = "\nWatchlist: " + (
        "; ".join(m.get("watch", "") for m in submitted_markets if m.get("watch"))
        or "none"
    )

    # RBP Opportunity Pass (§6.5)
    opp_block = ""
    if opportunity_pass:
        opp_block = (
            "\nRBP Opportunity Pass:\n"
            + "\n".join(
                f"  • {o['market']} | p={o['p']} | {o['label']} | {o['driver']} | crowd wrong: {o['why_crowd_wrong']}"
                for o in opportunity_pass.get("opportunities", [])
            )
        )

    return "\n".join([
        header,
        "\n".join(rows),
        edges,
        watchlist,
        batch_line,
        opp_block,
    ])


def _summarise_edges(markets: List[Dict]) -> str:
    """2-3 sentences on biggest edges."""
    high_conf = [m for m in markets if m.get("confidence") == "HIGH"]
    if high_conf:
        top = sorted(high_conf, key=lambda m: abs(m.get("p", 50) - 50), reverse=True)[:3]
        return "\nEdges: " + " · ".join(
            f"{m.get('question','')[:30]} p={m['p']} ({m.get('driver','')})"
            for m in top
        )
    return "\nEdges: no HIGH-confidence markets this batch"


# ---------------------------------------------------------------------------
# RBP SCOREBOARD (§8.3)
# ---------------------------------------------------------------------------

def rbp_scoreboard(
    results: List[Dict],
    crowd_brers: Optional[Dict[str, float]] = None,
    stage: str = "group",
) -> str:
    """
    crowd_brers: dict of market_id → crowd_brier (when available).
    D12: primary metric is weighted RBP.
    """
    from bot.config import STAGE_WEIGHTS

    weight = STAGE_WEIGHTS.get(stage, 1.0)
    settled = [r for r in results if r.get("brier_score") is not None]
    n = len(settled)
    if n == 0:
        return "RBP SCOREBOARD — no settled markets yet."

    total_rbp = 0.0
    beat_crowd = 0
    match_rbp: Dict[str, float] = {}
    worst = None
    best = None

    for r in settled:
        b = r["brier_score"]
        crowd_b = (crowd_brers or {}).get(r.get("market_id", ""), None)
        if crowd_b is not None:
            rbp = (crowd_b - b) * 100 * weight
            total_rbp += rbp
            if b < crowd_b:
                beat_crowd += 1
            mid = r.get("match_id", "?")
            match_rbp[mid] = match_rbp.get(mid, 0) + rbp
            if best is None or rbp > best[1]:
                best = (r, rbp)
            if worst is None or rbp < worst[1]:
                worst = (r, rbp)

    avg_rbp = total_rbp / n if n > 0 else 0

    best_match_key = max(match_rbp, key=match_rbp.get) if match_rbp else "n/a"
    worst_match_key = min(match_rbp, key=match_rbp.get) if match_rbp else "n/a"

    rows = [
        "| Metric                  | Value             |",
        "|-------------------------|-------------------|",
        f"| Settled markets         | {n}               |",
        f"| Total weighted RBP      | {total_rbp:+.2f}           |",
        f"| Avg RBP/market          | {avg_rbp:+.2f}           |",
        f"| Markets beat crowd      | {beat_crowd}/{n}           |",
        f"| Best match by RBP       | {best_match_key[:20]} {match_rbp.get(best_match_key, 0):+.1f} |",
        f"| Worst match by RBP      | {worst_match_key[:20]} {match_rbp.get(worst_match_key, 0):+.1f} |",
    ]
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# SETTLE AUDIT REPORT (§3.2 / §9.2)
# ---------------------------------------------------------------------------

def settle_audit_report(results: List[Dict], calibration_record) -> str:
    """
    Decode outcomes, compute Brier, identify worst-Brier markets for autopsy.
    """
    lines = ["SETTLE AUDIT"]
    newly_settled = [r for r in results if r.get("brier_score") is not None]

    if not newly_settled:
        lines.append("  No newly settled markets.")
        return "\n".join(lines)

    briers = [r["brier_score"] for r in newly_settled]
    avg_b = sum(briers) / len(briers)
    worst_b = max(newly_settled, key=lambda r: r["brier_score"])
    best_b  = min(newly_settled, key=lambda r: r["brier_score"])

    lines.append(f"  Settled: {len(newly_settled)} markets | Avg Brier: {avg_b:.4f}")

    # Outcome decoding (§9.2)
    decoded = []
    for r in newly_settled:
        p_sub = r.get("probability_submitted", r.get("probability", 0))
        if isinstance(p_sub, float) and p_sub <= 1:
            p_sub = int(round(p_sub * 100))
        outcome = decode_outcome_from_brier(p_sub, r["brier_score"])
        decoded.append({**r, "decoded_outcome": outcome})

    lines.append(f"  Best  Brier: {best_b['brier_score']:.4f} — {best_b.get('question','?')[:50]}")
    lines.append(f"  Worst Brier: {worst_b['brier_score']:.4f} — {worst_b.get('question','?')[:50]}")

    # Trigger deep audit threshold check (§9.5: every ~50–80 settled)
    total_settled = len(results)
    if total_settled > 0 and total_settled % 60 == 0:
        lines.append(f"\n  FLAG: Deep Audit due (n={total_settled} settled; threshold ~60).")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DEEP AUDIT REPORT (§9.5)
# ---------------------------------------------------------------------------

def deep_audit_report(
    results: List[Dict],
    calibration_record,
    lessons_ledger,
) -> str:
    """Full §9.5 periodic deep audit: per-match Brier table + 10pt band decomposition."""
    lines = ["PERIODIC DEEP AUDIT (§9.5)"]

    # Per-match Brier table
    match_briers: Dict[str, List[float]] = {}
    for r in results:
        if r.get("brier_score") is None:
            continue
        mid = r.get("match_id", "?")
        match_briers.setdefault(mid, []).append(r["brier_score"])

    lines.append("\nPer-match Brier:")
    sorted_matches = sorted(match_briers.items(), key=lambda x: sum(x[1]) / len(x[1]))
    for mid, briers in sorted_matches:
        avg = sum(briers) / len(briers)
        n   = len(briers)
        lines.append(f"  {mid[:20]:<22} n={n:>3} avg Brier={avg:.4f}")

    # 10pt probability-band decomposition
    lines.append("\n10pt band decomposition:")
    bands: Dict[str, List[float]] = {}
    for r in results:
        if r.get("brier_score") is None:
            continue
        p_sub = r.get("probability_submitted", r.get("probability", 0))
        if isinstance(p_sub, float) and p_sub <= 1:
            p_sub = int(round(p_sub * 100))
        band = f"{(p_sub // 10) * 10:02d}–{(p_sub // 10) * 10 + 9:02d}"
        bands.setdefault(band, []).append(r["brier_score"])

    for band, briers in sorted(bands.items()):
        avg = sum(briers) / len(briers)
        n   = len(briers)
        lines.append(f"  {band}: n={n:>3} avg Brier={avg:.4f}")

    # Calibration verdict
    all_briers = [r["brier_score"] for r in results if r.get("brier_score") is not None]
    if all_briers:
        realized = sum(all_briers) / len(all_briers)
        verdict = calibration_record.compute_verdicts(realized, 0.2173, len(all_briers))
        lines.append(f"\nCalibration: realized={realized:.4f} | {verdict}")

    return "\n".join(lines)
