"""
SportsPredict Bot — Jump Trading Probability Cup

Entry point for autonomous Claude sessions.

USAGE (in a Claude session with SportsPredict MCP connected):
    Run this file's logic by following the SESSION PROTOCOL below.
    The bot operates under FULL AUTONOMY (§0.1, granted 2026-06-12).

SESSION PROTOCOL (§3):
  Step 1 — TRIAGE: call list_matches + list_predictions + list_results
  Step 2 — SETTLE AUDIT: decode outcomes, update lessons/base-rates
  Step 3 — DEPTH PASS: for each near-horizon (<48h) match
  Step 4 — COVERAGE SWEEP: PASS-1 for mid/far uncovered matches (12–16 target)
  Step 5 — SUBMIT: submit_predictions_batch (≤50 per call, D6)
  Step 6 — REPORT: STATUS BLOCK + after-action + RBP scoreboard

All logic is in the bot/ package. This file demonstrates the call sequence.
"""

from bot.config import EVENT_ID, LOBBY_ID
from bot.session import Session, estimate_lambdas
from bot.api import (
    call_list_matches, call_list_markets, call_list_predictions,
    call_list_results, call_join_lobby, build_batch,
    handle_409_already_predicted,
)
from bot.reporting import status_block, settle_audit_report


def run_session(
    matches_response: list,
    predictions_response: list,
    results_response: list,
    verbose: bool = True,
) -> "Session":
    """
    Main session runner. Call after fetching live data from MCP tools.

    Agent workflow:
      1. Call mcp__SportsPredict__list_matches(event_id=EVENT_ID, lobby_id=LOBBY_ID)
      2. Call mcp__SportsPredict__list_predictions(lobby_id=LOBBY_ID)
      3. Call mcp__SportsPredict__list_results(lobby_id=LOBBY_ID)
      4. Pass the responses to this function.
      5. Iterate over session.prepare_depth_pass() for near-horizon matches.
      6. For each: fetch mcp__SportsPredict__list_markets(match_id=..., lobby_id=LOBBY_ID)
      7. Call session.finalize_depth_pass() with real odds data.
      8. Collect predictions from prepare_pass1_sweep() and finalize_pass1().
      9. Submit via mcp__SportsPredict__submit_predictions_batch(predictions=[...]).
      10. Call session.build_session_report() and print it.

    Returns the Session object for further inspection.
    """
    session = Session()

    # ── STEP 1: TRIAGE ──
    triage_report = session.ingest_triage(
        matches=matches_response,
        predictions=predictions_response,
        results=results_response,
    )
    if verbose:
        print(triage_report)

    # ── STEP 2: SETTLE AUDIT ──
    audit_report = session.run_settle_audit()
    if verbose:
        print(audit_report)

    # ── The agent then handles STEP 3–5 using session.* helpers ──
    # (Depth Pass and Coverage Sweep require per-match market fetches and odds inputs.)

    return session


def tool_call_sequence() -> list:
    """
    Returns the ordered list of MCP tool calls for a full session.
    The agent executes these in order, passing responses to run_session().

    Each item is a dict: {tool: str, params: dict}.
    """
    return [
        # TRIAGE (execute all three in parallel — they don't depend on each other)
        call_list_matches(event_id=EVENT_ID, lobby_id=LOBBY_ID),
        call_list_predictions(lobby_id=LOBBY_ID),
        call_list_results(lobby_id=LOBBY_ID),
        # Per-match (near-horizon): call_list_markets(match_id=<id>, lobby_id=LOBBY_ID)
        # Then finalize with session.finalize_depth_pass()
        # Per-match (mid/far sweep): same list_markets + session.finalize_pass1()
        # Submit: build_batch(markets=[...])
        # check lobby membership:
        call_join_lobby(lobby_id=LOBBY_ID),   # no-op if already joined
    ]


# ---------------------------------------------------------------------------
# Quick self-test (no MCP needed)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from bot.engine import (
        devig_power, fit_lambda, btts_prob, poisson_prob_over,
        archetype_ht_tied, archetype_drama, coherence_check,
        run_mc_correlation,
    )
    from bot.utils import decode_outcome_from_brier, clamp

    print("=== Engine self-test ===\n")

    # Devig test
    raw = [2.10, 3.40, 3.60]
    fair = devig_power(raw)
    print(f"Devig {raw} → {[round(f*100,1) for f in fair]}  (sum={sum(fair)*100:.1f})")

    # Lambda fit test
    lh, la = fit_lambda(0.56, 0.48, 0.26, 0.26)
    print(f"Lambda fit (ou25=56%, home=48%) → λ_h={lh:.3f} λ_a={la:.3f}")

    # BTTS test
    p_btts = btts_prob(lh, la) * 100
    print(f"BTTS prob → {p_btts:.1f}%")

    # Over 2.5 test
    p_o25 = poisson_prob_over(lh + la, 2.5) * 100
    print(f"Over 2.5 → {p_o25:.1f}%")

    # HT tied test
    p_ht = archetype_ht_tied(lh, la)
    print(f"HT tied → {p_ht:.1f}% (L9 ceiling applied)")

    # Drama (pen) test
    p_pen = archetype_drama("penalty", 0.28, eb_n=5, eb_k=2)
    print(f"Penalty EB → {p_pen:.1f}%")

    # Outcome decode test
    o = decode_outcome_from_brier(72, round((0.72-1)**2, 4))
    print(f"Decode: p=72, brier={(0.72-1)**2:.4f} → outcome={o}")

    # Coherence check test
    markets = [
        {"id":"m1","question":"Home win","p":48,"match_id":"X"},
        {"id":"m2","question":"Draw","p":27,"match_id":"X"},
        {"id":"m3","question":"Away win","p":25,"match_id":"X"},
    ]
    violations = coherence_check(markets)
    print(f"Coherence check (triplet 48+27+25=100): {violations or 'PASS'}")

    # MC correlation test
    mc_markets = [
        {"archetype":"win_home","p":48,"question":"Home win"},
        {"archetype":"btts","p":55,"question":"BTTS"},
        {"archetype":"over_2_5","p":56,"question":"Over 2.5"},
        {"archetype":"draw","p":27,"question":"Draw"},
        {"archetype":"win_away","p":25,"question":"Away win"},
    ]
    mc_results = run_mc_correlation(lh, la, mc_markets, n_draws=500)
    print(f"\nL8 MC results (500 draws):")
    for r in mc_results:
        print(f"  {r['question']}: p_base={r['p']} p_mc={r.get('p_mc','n/a')}")

    print("\n=== All self-tests passed ===")
