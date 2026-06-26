"""
Jump Trading Probability Cup — Reporting format generators (§8).

Produces:
  §8.1  STATUS BLOCK (opens every session)
  §8.2  AFTER-ACTION REPORT (per match, per autonomous write)
  §8.3  DEPTH PASS delta report
  §8.4  RBP SCOREBOARD BLOCK
  §6.5  RBP OPPORTUNITY PASS table
  §9.5  DEEP AUDIT summary

All output is plain text / Markdown tables for pasting into chat.
No MCP calls; pass in already-computed data.
"""

import math
from engine import self_expected_brier, brier_noise_band, rbp_market, decode_outcome


# ---------------------------------------------------------------------------
# §8.1  STATUS BLOCK
# ---------------------------------------------------------------------------

def status_block(
    date_ist,
    settled_since_last,
    session_realized_brier,
    session_self_expected_brier,
    near_horizon_rows,
    mid_far_rows,
    actions_taken,
    flags,
    next_checkin,
):
    """
    Generate the STATUS BLOCK that opens every session. §8.1

    Parameters:
        date_ist (str): current datetime in IST, e.g. "2026-06-26 14:30 IST"
        settled_since_last (int): newly settled markets since last session
        session_realized_brier (float|None): mean Brier over settled markets
        session_self_expected_brier (float|None): self-expected Brier
        near_horizon_rows (list[dict]):
            each: {name, kickoff (str), depth_pass_done (bool)}
        mid_far_rows (list[dict]):
            each: {name, kickoff (str), state (str)}
        actions_taken (dict):
            {depth_pass: {matches: n, markets: n}, sweep: {matches: n, markets: n}, topups: n}
        flags (list[str]): e.g. ["STATE PULL TRUNCATED", "Deep audit due (§9.5)"]
        next_checkin (str): pre-formatted "NEXT CHECK-IN BY: …"

    Returns: str
    """
    lines = [f"STATUS — {date_ist}"]

    if session_realized_brier is not None and session_self_expected_brier is not None:
        gap = session_realized_brier - session_self_expected_brier
        sign = "+" if gap >= 0 else ""
        direction = "↑ worse" if gap > 0 else "↓ better"
        lines.append(
            f"Settled since last: {settled_since_last} markets | "
            f"session Brier {session_realized_brier:.3f} vs self-expected {session_self_expected_brier:.3f} "
            f"(gap {sign}{gap:.3f} {direction}) | cum RBP: leaderboard lags ≤1h"
        )
    else:
        lines.append(
            f"Settled since last: {settled_since_last} markets | "
            "Brier unavailable this session | cum RBP: leaderboard lags ≤1h"
        )

    if near_horizon_rows:
        lines.append("Near horizon (<48h, IST):")
        for r in near_horizon_rows:
            dp = "Y" if r.get("depth_pass_done") else "N"
            lines.append(f"  {r['name']} — {r['kickoff']} — Depth Pass done: {dp}")

    if mid_far_rows:
        lines.append("Mid/far horizon (≤7d, IST):")
        for r in mid_far_rows:
            lines.append(f"  {r['name']} — {r['kickoff']} — {r['state']}")

    at = actions_taken or {}
    dp = at.get("depth_pass", {})
    sw = at.get("sweep", {})
    lines.append(
        f"Actions taken this session: "
        f"Depth Pass: {dp.get('matches', 0)} matches / {dp.get('markets', 0)} markets · "
        f"Coverage sweep: {sw.get('matches', 0)} matches / {sw.get('markets', 0)} markets · "
        f"top-ups: {at.get('topups', 0)}"
    )

    if flags:
        lines.append(f"Flags: {' · '.join(flags)}")
    else:
        lines.append("Flags: none")

    lines.append(next_checkin)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §8.2  AFTER-ACTION REPORT (per match)
# ---------------------------------------------------------------------------

def after_action_report(
    match_name,
    kickoff_ist,
    stage_weight,
    horizon,
    mode_mix,
    market_predictions,
    batch_result,
    top_edges,
    watchlist,
):
    """
    Per-match after-action report. §8.2

    Parameters:
        match_name (str): e.g. "BRA vs ARG"
        kickoff_ist (str): e.g. "2026-06-26 20:00 IST"
        stage_weight (int): 1 / 2 / 3
        horizon (str): 'near' / 'mid' / 'far'
        mode_mix (str): e.g. "60% ANCHORED / 40% MODELED"
        market_predictions (list[dict]):
            each: {market (str), mode (str), p (int), conf (str), driver (str)}
        batch_result (dict):
            {succeeded (int), failed (int), prediction_ids (list[str])}
        top_edges (list[str]): 2-3 sentences on biggest expected-RBP edges
        watchlist (list[dict]):
            each: {market (str), trigger (str), when (str)}

    Returns: str
    """
    lines = [
        f"### {match_name}",
        f"Kickoff: {kickoff_ist} · Stage {stage_weight}× · Horizon: {horizon} · {mode_mix}",
        "",
    ]

    col_w = [3, 35, 10, 4, 8, 0]
    header = f"{'#':<{col_w[0]}} {'Market':<{col_w[1]}} {'Mode':<{col_w[2]}} {'p':>{col_w[3]}} {'Conf':<{col_w[4]}} {'Driver'}"
    lines.append(header)
    lines.append("-" * min(len(header) + 30, 110))

    for i, mp in enumerate(market_predictions, 1):
        lines.append(
            f"{i:<{col_w[0]}} "
            f"{mp['market']:<{col_w[1]}} "
            f"{mp['mode']:<{col_w[2]}} "
            f"{mp['p']:>{col_w[3]}}  "
            f"{mp['conf']:<{col_w[4]}} "
            f"{mp['driver']}"
        )

    lines.append("")
    if top_edges:
        lines.append("**Biggest edges:**")
        for edge in top_edges:
            lines.append(f"  {edge}")
        lines.append("")

    if watchlist:
        lines.append("**Watchlist** (news that would move any number ≥3):")
        for w in watchlist:
            lines.append(f"  {w['market']}: {w['trigger']} | when: {w['when']}")
        lines.append("")

    r = batch_result or {}
    succeeded = r.get("succeeded", "?")
    failed = r.get("failed", 0)
    lines.append(f"**Batch:** {succeeded} succeeded · {failed} failed")
    ids = r.get("prediction_ids") or []
    if ids:
        sample = ", ".join(str(pid) for pid in ids[:5])
        suffix = f" … (+{len(ids)-5} more)" if len(ids) > 5 else ""
        lines.append(f"  IDs: {sample}{suffix}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §8.3  DEPTH PASS delta report
# ---------------------------------------------------------------------------

def depth_pass_delta(match_name, changes, unchanged_count):
    """
    Depth Pass delta: only changed markets. §8.3

    Parameters:
        match_name (str)
        changes (list[dict]): each {market (str), old_p (int), new_p (int), driver (str)}
        unchanged_count (int): markets re-verified with no Δ ≥ threshold

    Returns: str
    """
    lines = [f"**Depth Pass delta — {match_name}**"]

    if changes:
        lines.append(f"{'Market':<35} {'Old':>4}  {'New':<4} {'Driver'}")
        lines.append("-" * 75)
        for c in changes:
            arrow = "→"
            lines.append(
                f"{c['market']:<35} {c['old_p']:>3}  {arrow} {c['new_p']:<3} {c['driver']}"
            )
    if unchanged_count > 0:
        lines.append(f"{unchanged_count} market(s) re-verified, no Δ ≥ threshold")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §8.4  RBP SCOREBOARD BLOCK
# ---------------------------------------------------------------------------

def rbp_scoreboard(
    settled_count,
    your_briers,
    crowd_briers=None,
    stage_weights=None,
    best_match=None,
    worst_match=None,
    best_brier_match=None,
):
    """
    RBP scoreboard block. §8.4 — leads with RBP, raw Brier is secondary.

    Parameters:
        settled_count (int)
        your_briers (list[float]): per-market Brier scores
        crowd_briers (list[float]|None): crowd Brier per market (if available)
        stage_weights (list[int]|None): per-market stage weights (default 1)
        best_match (dict|None): {name, rbp}
        worst_match (dict|None): {name, rbp}
        best_brier_match (dict|None): {name, brier}

    Returns: str
    """
    sw = stage_weights or [1] * len(your_briers)

    if crowd_briers and your_briers:
        weighted_rbps = [rbp_market(cb, yb, w) for cb, yb, w in zip(crowd_briers, your_briers, sw)]
        total_rbp = sum(weighted_rbps)
        avg_rbp = total_rbp / settled_count if settled_count else 0
        beat_crowd = sum(1 for yb, cb in zip(your_briers, crowd_briers) if yb < cb)
        rbp_available = True
    else:
        total_rbp = avg_rbp = None
        beat_crowd = None
        rbp_available = False

    def _row(metric, value):
        return f"| {metric:<25} | {value:<38} |"

    lines = [
        f"| {'Metric':<25} | {'Value':<38} |",
        "|" + "-" * 27 + "|" + "-" * 40 + "|",
        _row("Settled markets audited", str(settled_count)),
    ]

    if rbp_available:
        lines.append(_row("Total weighted RBP", f"{total_rbp:.2f}"))
        lines.append(_row("Avg RBP / market", f"{avg_rbp:.2f}"))
        lines.append(_row("Markets beat crowd", f"{beat_crowd} / {settled_count}"))
    else:
        lines.append(_row("Total weighted RBP", "unavailable — no crowd_brier"))
        lines.append(_row("Markets beat crowd", "RBP unavailable"))

    if best_match:
        lines.append(_row("Best match by RBP", f"{best_match['name']} ({best_match['rbp']:+.2f})"))
    if worst_match:
        lines.append(_row("Worst match by RBP", f"{worst_match['name']} ({worst_match['rbp']:+.2f})"))
    if best_brier_match:
        lines.append(_row("Best raw-Brier match", f"{best_brier_match['name']} (Brier {best_brier_match['brier']:.3f}) [secondary]"))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §6.5  RBP OPPORTUNITY PASS table
# ---------------------------------------------------------------------------

def opportunity_pass_table(markets):
    """
    RBP Opportunity Pass table per §6.5.

    markets: list[dict] with keys:
        market (str), p (int), opportunity (str), driver (str), why_crowd_wrong (str)

    Returns: str
    """
    lines = [
        f"{'Market':<35} {'p':>4}  {'Opp':<10} {'Driver':<30} {'Why crowd may be wrong'}",
        "-" * 120,
    ]
    for m in sorted(markets, key=lambda x: {"STRONG": 0, "MODERATE": 1, "THIN": 2, "UNKNOWN": 3}.get(x.get("opportunity","UNKNOWN"), 3)):
        lines.append(
            f"{m['market']:<35} {m['p']:>3}  "
            f"{m['opportunity']:<10} "
            f"{m['driver']:<30} "
            f"{m['why_crowd_wrong']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §9.5  DEEP AUDIT summary
# ---------------------------------------------------------------------------

def deep_audit_summary(
    n_settled,
    your_briers,
    per_match_briers,
    band_decomp,
    crowd_briers=None,
    stage_weights=None,
):
    """
    Periodic Deep Audit summary per §9.5 (+ §9.6 when crowd_briers available).

    Parameters:
        n_settled (int): total settled markets in this audit
        your_briers (list[float]): per-market Brier
        per_match_briers (dict): {match_name: avg_brier}
        band_decomp (dict): {band_str: {n, hit_rate, avg_submitted}} e.g. "50-55"
        crowd_briers (list[float]|None)
        stage_weights (list[int]|None)

    Returns: str
    """
    realized = sum(your_briers) / len(your_briers) if your_briers else 0
    p_list = []  # we'd need the submitted p values; use realized as fallback
    self_exp = self_expected_brier(p_list) if p_list else None
    noise = brier_noise_band(n_settled)

    lines = [f"## Deep Audit @{n_settled} settled"]

    # Calibration line
    if self_exp:
        gap = realized - self_exp
        sigma_lo = gap / 0.18 if 0.18 else None
        sigma_hi = gap / 0.12 if 0.12 else None
        lines.append(
            f"Realized {realized:.4f} vs self-expected {self_exp:.4f} → "
            f"gap {gap:+.4f} | ~{sigma_lo:.1f}–{sigma_hi:.1f}σ | noise band ±{noise:.3f}"
        )
    else:
        lines.append(f"Realized Brier: {realized:.4f} (self-expected requires submitted p values)")

    # Per-match Brier table
    if per_match_briers:
        lines.append("\n### Per-match Brier (dominant variance axis, §9.5)")
        sorted_matches = sorted(per_match_briers.items(), key=lambda x: x[1])
        lines.append(f"{'Match':<30} {'Avg Brier':>10}")
        lines.append("-" * 42)
        for name, brier in sorted_matches:
            lines.append(f"{name:<30} {brier:>10.3f}")
        best = sorted_matches[0]
        worst = sorted_matches[-1]
        spread = worst[1] - best[1]
        lines.append(
            f"\nSpread: {spread:.3f} — check match-level λ/T/L8 quality before archetype tuning (§9.5)"
        )

    # Band decomposition
    if band_decomp:
        lines.append("\n### Probability-band decomposition (§9.5)")
        lines.append(f"{'Band':<10} {'n':>5}  {'Avg sub':>8}  {'Hit rate':>9}  {'Gap':>7}  {'Action'}")
        lines.append("-" * 65)
        for band, d in sorted(band_decomp.items()):
            gap_pts = d.get("hit_rate", 0) * 100 - d.get("avg_submitted", 50)
            flag = ""
            if abs(gap_pts) >= 8 and d.get("n", 0) >= 8:
                flag = "→ ACTIVE candidate"
            elif abs(gap_pts) >= 8:
                flag = "→ PROVISIONAL (n<8)"
            lines.append(
                f"{band:<10} {d.get('n', 0):>5}  {d.get('avg_submitted', 0):>7.1f}  "
                f"{d.get('hit_rate', 0)*100:>8.1f}%  {gap_pts:>+7.1f}  {flag}"
            )

    # RBP section (§9.6)
    if crowd_briers and your_briers:
        sw = stage_weights or [1] * len(your_briers)
        rbps = [rbp_market(cb, yb, w) for cb, yb, w in zip(crowd_briers, your_briers, sw)]
        total_rbp = sum(rbps)
        avg_rbp = total_rbp / n_settled
        beat = sum(1 for r in rbps if r > 0)
        lines.append("\n### RBP summary (§9.6)")
        lines.append(f"Total weighted RBP: {total_rbp:.2f} | Avg: {avg_rbp:.2f} | Beat crowd: {beat}/{n_settled}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# §9.3  Worst-Brier autopsy helper
# ---------------------------------------------------------------------------

_BRIER_TAXONOMY = [
    "bad anchor",
    "missed news/lineup",
    "wording misread",
    "tie-trap miss",
    "λ/T misread",
    "correlated-axis hit (L8)",
    "pure noise (no fix)",
]


def autopsy_template(rank, market_name, brier_score, submitted_p, outcome):
    """Return a one-line autopsy template for the top-3 worst Briers. §9.3"""
    from engine import decode_outcome
    o = outcome if outcome is not None else decode_outcome(submitted_p / 100, brier_score)
    return (
        f"#{rank}  {market_name}  p={submitted_p} o={o}  Brier={brier_score:.3f}  "
        f"diagnosis: [choose: {' / '.join(_BRIER_TAXONOMY)}]"
    )


if __name__ == "__main__":
    print("=== Reporting self-test ===")

    # STATUS BLOCK
    sb = status_block(
        date_ist="2026-06-26 14:30 IST",
        settled_since_last=12,
        session_realized_brier=0.228,
        session_self_expected_brier=0.215,
        near_horizon_rows=[
            {"name": "BRA vs ARG", "kickoff": "2026-06-26 20:00 IST", "depth_pass_done": False},
        ],
        mid_far_rows=[
            {"name": "ESP vs GER", "kickoff": "2026-06-27 23:30 IST", "state": "COVERED-STALE"},
        ],
        actions_taken={"depth_pass": {"matches": 1, "markets": 9}, "sweep": {"matches": 3, "markets": 28}, "topups": 2},
        flags=["Deep audit due (§9.5) — 48 newly settled since last"],
        next_checkin="NEXT CHECK-IN BY: 2026-06-27 14:30 IST (informational — confirmed daily cadence §2.4)",
    )
    print(sb)
    print()

    # RBP scoreboard
    rs = rbp_scoreboard(
        settled_count=12,
        your_briers=[0.18, 0.22, 0.31, 0.19, 0.25],
        crowd_briers=[0.24, 0.28, 0.35, 0.22, 0.30],
        best_match={"name": "BRA vs ARG", "rbp": 42.3},
        worst_match={"name": "QAT vs SUI", "rbp": -8.1},
        best_brier_match={"name": "GER vs CUR", "brier": 0.132},
    )
    print(rs)
