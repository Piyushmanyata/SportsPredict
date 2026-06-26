"""
Report formatters (§8).

STATUS BLOCK (§8.1) · AFTER-ACTION REPORT (§8.2) · RBP SCOREBOARD (§8.4).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from constants import IST_OFFSET_HOURS

IST = timezone(timedelta(hours=IST_OFFSET_HOURS))


def now_ist() -> str:
    return datetime.now(IST).strftime("%d %b %Y %H:%M IST")


def status_block(
    triaged_matches: list,       # list[MatchTriage]
    settled_since_last_n: int,
    session_brier: float | None,
    self_expected_brier: float | None,
    actions_taken: dict | None = None,
    flags: list[str] | None = None,
    next_checkin_ist: str | None = None,
) -> str:
    """
    Format the STATUS BLOCK that opens every session (§8.1).
    """
    lines = []
    lines.append(f"STATUS — {now_ist()}")
    lines.append(
        f"Settled since last: {settled_since_last_n} markets | "
        + (f"session Brier {session_brier:.3f} vs self-expected {self_expected_brier:.3f}"
           if session_brier is not None else "Brier: N/A")
    )

    # Near horizon (<48h)
    near = [m for m in triaged_matches if m.horizon.value == "near"]
    if near:
        lines.append("Near horizon (<48h, IST):")
        for m in near:
            dp_flag = "Y" if m.depth_pass_done else "N"
            kick_ist = m.kickoff_ist.strftime("%d %b %H:%M IST")
            lines.append(f"  {m.name} — {kick_ist} — {m.state} — DP done? {dp_flag}")
    else:
        lines.append("Near horizon: none")

    # Mid/far (≤7d)
    mid_far = [m for m in triaged_matches if m.horizon.value in ("mid", "far")]
    if mid_far:
        lines.append("Mid/far horizon (≤7d, IST):")
        for m in mid_far[:16]:  # cap display
            kick_ist = m.kickoff_ist.strftime("%d %b %H:%M IST")
            lines.append(f"  {m.name} — {kick_ist} — {m.state}")

    # Actions taken
    if actions_taken:
        dp  = actions_taken.get("depth_pass", {})
        cs  = actions_taken.get("coverage_sweep", {})
        ups = actions_taken.get("top_ups", 0)
        lines.append(
            f"Actions this session: "
            f"Depth Pass: {dp.get('matches',0)} matches / {dp.get('markets',0)} markets · "
            f"Coverage sweep: {cs.get('matches',0)} matches / {cs.get('markets',0)} markets · "
            f"Top-ups: {ups}"
        )

    # Flags
    if flags:
        lines.append("Flags:")
        for f in flags:
            lines.append(f"  ⚑ {f}")

    # Next check-in
    if next_checkin_ist:
        lines.append(f"NEXT CHECK-IN BY: {next_checkin_ist} (informational, confirmed daily cadence)")
    else:
        nxt = (datetime.now(IST) + timedelta(hours=24)).strftime("%d %b %H:%M IST")
        lines.append(f"NEXT CHECK-IN BY: {nxt} (informational, confirmed daily cadence)")

    return "\n".join(lines)


def after_action_report(
    match_name: str,
    kickoff_ist: str,
    stage_weight: float,
    horizon: str,
    markets_table: list[dict],     # {#, market, mode, p, conf, driver}
    batch_result: dict | None = None,
    edge_notes: list[str] | None = None,
    watchlist: list[str] | None = None,
) -> str:
    """
    Format the AFTER-ACTION REPORT (§8.2) for one match.
    """
    lines = []
    lines.append(f"=== AFTER-ACTION: {match_name} ===")
    lines.append(f"Kickoff: {kickoff_ist} | Stage weight: {stage_weight}× | Horizon: {horizon}")
    lines.append("")

    # Market table
    lines.append(f"{'#':<4} {'Market':<32} {'Mode':<12} {'p':>4} {'Conf':<8} Driver")
    lines.append("-" * 80)
    for i, row in enumerate(markets_table, 1):
        lines.append(
            f"{i:<4} {row.get('market',''):<32} {row.get('mode',''):<12} "
            f"{row.get('p',0):>4} {row.get('conf',''):<8} {row.get('driver','')}"
        )

    # Biggest edges
    if edge_notes:
        lines.append("")
        lines.append("Biggest edges:")
        for note in edge_notes[:3]:
            lines.append(f"  • {note}")

    # Watchlist
    if watchlist:
        lines.append("")
        lines.append("Watchlist (would move any number ≥3):")
        for item in watchlist:
            lines.append(f"  → {item}")

    # Batch confirmation
    if batch_result:
        lines.append("")
        ok  = batch_result.get("succeeded", "?")
        err = batch_result.get("failed", 0)
        lines.append(f"Batch: {ok} submitted · {err} failed")
        ids = batch_result.get("prediction_ids", [])
        if ids:
            lines.append(f"  IDs: {', '.join(str(i) for i in ids[:5])}{'...' if len(ids)>5 else ''}")

    return "\n".join(lines)


def rbp_scoreboard(
    audited_markets: int,
    total_weighted_rbp: float | None,
    markets_beat_crowd: int | None,
    best_match: tuple[str, float] | None,   # (name, rbp)
    worst_match: tuple[str, float] | None,
    best_brier_match: tuple[str, float] | None,
) -> str:
    """
    Format the RBP SCOREBOARD (§8.4) that opens every settle/deep audit.
    """
    def _fmt(v):
        return f"{v:.2f}" if v is not None else "N/A"

    avg_rbp = (total_weighted_rbp / audited_markets) if (total_weighted_rbp and audited_markets) else None

    lines = [
        "RBP SCOREBOARD",
        f"  Settled markets audited : {audited_markets}",
        f"  Total weighted RBP      : {_fmt(total_weighted_rbp)}",
        f"  Avg RBP / market        : {_fmt(avg_rbp)}",
        f"  Markets beat crowd      : {markets_beat_crowd if markets_beat_crowd is not None else 'N/A'} / {audited_markets}",
        f"  Best match by RBP       : {best_match[0] + ' ' + _fmt(best_match[1]) if best_match else 'N/A'}",
        f"  Worst match by RBP      : {worst_match[0] + ' ' + _fmt(worst_match[1]) if worst_match else 'N/A'}",
        f"  Best raw-Brier match    : {best_brier_match[0] + ' avg ' + _fmt(best_brier_match[1]) if best_brier_match else 'N/A'} (secondary)",
    ]
    return "\n".join(lines)


def depth_pass_delta_report(changed_markets: list[dict], unchanged_n: int) -> str:
    """
    §8.3 — Depth Pass delta report: only changed markets.
    changed_markets: [{market, old_p, new_p, driver}]
    """
    if not changed_markets:
        return f"{unchanged_n} markets re-verified, no Δ ≥ 3."

    lines = [f"{'Market':<32} {'Old':>5} {'New':>5} Driver"]
    lines.append("-" * 65)
    for m in changed_markets:
        lines.append(
            f"{m['market']:<32} {m['old_p']:>5} {m['new_p']:>5} {m.get('driver','')}"
        )
    if unchanged_n:
        lines.append(f"\n{unchanged_n} markets re-verified, no Δ ≥ 3.")
    return "\n".join(lines)
