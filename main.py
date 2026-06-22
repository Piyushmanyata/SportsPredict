#!/usr/bin/env python3
"""
SportsPredict Bot — Session Entry Point & Self-Test
Jump Trading Probability Cup (June 11–July 19, 2026)

Run once per session. Validates the engine, prints key constants,
and provides the reference session flow for Claude to orchestrate
using the SportsPredict MCP tools.

Usage:
  python main.py
"""

import sys


def main() -> None:
    print("=" * 60)
    print("SportsPredict Probability Engine v3")
    print("Jump Trading Probability Cup")
    print("=" * 60)

    # ── Module imports ────────────────────────────────────────────
    from state import EVENT_ID, LOBBY_ID, TOURNAMENT, BASE_RATES, LESSONS
    from engine import (
        power_devig, devig_3way, ou25_to_T, fit_lambda_split, batch_mc,
        market_btts_3plus, market_ht_tied, market_totals, tie_trap_market,
        market_cards_ge4, player_sot_prob, drama_market_prob,
        coherence_check, apply_l10_driver_gate, to_int,
        dixon_coles_draw_adjust,
    )
    from session import (
        classify_market, opportunity_label, derive_match_probabilities,
        build_batch_payload, should_run_mc, build_mc_input,
    )
    from feedback import (
        decode_outcome, self_expected_brier, calibration_verdict,
        band_decomposition, compute_rbp, cost_of_distortion,
    )
    from report import status_block, rbp_scoreboard, now_ist

    # ── Constants ────────────────────────────────────────────────
    print(f"\nEvent ID:  {EVENT_ID}")
    print(f"Lobby ID:  {LOBBY_ID}")
    print(f"Tournament: {TOURNAMENT['name']}")
    print(f"Markets:    ~{TOURNAMENT['markets_approx']}")
    print(f"Base goals/match: {BASE_RATES['goals_per_match_group']}")
    print(f"Lessons active:   {sum(1 for l in LESSONS.values() if l['grade'] == 'ACTIVE')}")
    print(f"Lessons confirmed:{sum(1 for l in LESSONS.values() if l['grade'] == 'CONFIRMED')}")

    # ── Engine self-test ─────────────────────────────────────────
    print("\n── Engine Self-Test ──")
    errors = []

    # 1. Power devig
    dv = power_devig([0.55, 0.30, 0.20])
    assert abs(sum(dv) - 1.0) < 0.001, "power_devig sum != 1"
    print(f"  power_devig([0.55,0.30,0.20]) → {[round(x,3) for x in dv]} ✓")

    # 2. 3-way devig
    pa, pd, pb = devig_3way(0.50, 0.29, 0.25)
    assert abs(pa + pd + pb - 1.0) < 0.001
    print(f"  devig_3way(0.50,0.29,0.25) → A={pa:.3f} D={pd:.3f} B={pb:.3f} ✓")

    # 3. L12 Dixon-Coles adjustment
    pa2, pd2, pb2 = dixon_coles_draw_adjust(0.48, 0.27, 0.25)
    assert pd2 > 0.27, "DC should increase draw in 40-60 band"
    print(f"  Dixon-Coles adj (L12) → draw {0.27:.3f} → {pd2:.3f} ✓")

    # 4. O/U → T
    T = ou25_to_T(0.46)
    assert abs(T - 2.5) < 0.01, f"Expected T≈2.5, got {T}"
    print(f"  ou25_to_T(0.46) → T={T:.2f} ✓")

    # 5. λ split
    la, lb = fit_lambda_split(2.7, 0.45, 0.26, 0.29)
    assert abs(la + lb - 2.7) < 0.05, f"λ sum {la+lb:.2f} != 2.7"
    print(f"  fit_lambda_split(2.7) → λ_A={la:.2f}, λ_B={lb:.2f} ✓")

    # 6. BTTS^3+
    btts3 = market_btts_3plus(la, lb)
    assert 0 < btts3 < 1
    print(f"  btts3plus({la:.2f},{lb:.2f}) → {to_int(btts3)}% ✓")

    # 7. HT tied (L9 ceiling check)
    ht = market_ht_tied(la, lb)
    assert ht <= 0.47, f"L9 ceiling violated: {ht:.3f} > 0.47"
    print(f"  ht_tied({la:.2f},{lb:.2f}) → {to_int(ht)}% (≤47) ✓")

    # 8. Tie-trap (L3 — never 50 for even matchup)
    tt = tie_trap_market('corners_ft', 1.0)
    assert tt < 50, f"Tie-trap even matchup should be < 50, got {tt}"
    print(f"  tie_trap('corners_ft', even) → {tt}% (< 50) ✓")

    # 9. Cards table
    c = market_cards_ge4(3.5)
    assert abs(c - 0.46) < 0.01, f"Expected 0.46, got {c:.3f}"
    print(f"  market_cards_ge4(3.5) → {to_int(c)}% (expected 46) ✓")

    # 10. Player SOT + L10 driver gate
    p_sot = player_sot_prob(12.0, 0.25, 'ft')
    p_gated = apply_l10_driver_gate(p_sot, has_driver=False)
    print(
        f"  player_sot(λ_sot=12.0, share=0.25) → {to_int(p_sot)}% "
        f"→ L10-gated (no driver) → {to_int(p_gated)}% ✓"
    )

    # 11. Drama base-rate + EB
    dp = drama_market_prob(BASE_RATES['penalty_awarded_per_match'])
    assert 0.15 <= dp <= 0.85, f"Drama outside clamp: {dp:.3f}"
    print(f"  drama_market(pen) → {to_int(dp)}% (clamp 15–85) ✓")

    # 12. Coherence check
    cc = coherence_check(pa, pd, pb)
    assert cc['pass'], f"Coherence failed: {cc['issues']}"
    print(f"  coherence_check → pass ✓")

    # 13. L8 batch MC
    mc_input = [build_mc_input('test', la, lb,
                               ['btts3plus', 'clean_sheet_a', 'scores_2h_a',
                                'ht_tied', 'over25', 'under25'])]
    mc_out = batch_mc(mc_input, n_draws=1000, seed=0)
    assert 'test' in mc_out
    assert all(k in mc_out['test'] for k in
               ('btts3plus', 'clean_sheet_a', 'scores_2h_a', 'ht_tied'))
    print(f"  batch_mc → btts3plus={to_int(mc_out['test']['btts3plus'])}% "
          f"  clean_sheet_a={to_int(mc_out['test']['clean_sheet_a'])}% ✓")

    # 14. Feedback: outcome decoding
    assert decode_outcome(60, (0.60 - 1.0) ** 2) == 1
    assert decode_outcome(60, 0.60 ** 2) == 0
    print(f"  decode_outcome(60, Brier_YES) → 1 ✓  decode_outcome(60, Brier_NO) → 0 ✓")

    # 15. Market classifier
    assert classify_market("Will Germany win the match?") == 'win'
    assert classify_market("3 or more total goals") == 'totals'
    assert classify_market("Both teams score AND 3+ total goals") == 'btts3plus'
    assert classify_market("Will Germany score in the second half?") == 'scores_2h'
    assert classify_market("Will Germany have more corners than Spain?") == 'strict_compare'
    assert classify_market("Will a penalty be awarded?") == 'drama'
    print(f"  classify_market → 6 archetypes ✓")

    # 16. Cost-of-distortion guard
    cost = cost_of_distortion(10, 300)
    assert abs(cost['total_over_n'] - 300.0) < 0.1, f"Cost {cost['total_over_n']} != 300"
    print(f"  cost_of_distortion(10pp, 300 mkts) → {cost['total_over_n']} RBP ✓")

    # 17. Full derive pipeline (mock research)
    mock_markets = [
        {'id': 'mkt-1', 'question': 'Will Germany win the match?'},
        {'id': 'mkt-2', 'question': '3 or more total goals'},
        {'id': 'mkt-3', 'question': 'Both teams score AND 3+ total goals'},
        {'id': 'mkt-4', 'question': 'Will Germany score in the second half?'},
        {'id': 'mkt-5', 'question': 'Will Germany have more corners than Spain?'},
        {'id': 'mkt-6', 'question': 'Will a penalty be awarded?'},
    ]
    mock_research = {
        'p_win_a_implied': 0.55, 'p_draw_implied': 0.28, 'p_win_b_implied': 0.23,
        'p_over25_implied': 0.52,
        'team_a': 'germany', 'team_b': 'spain',
        'stage': 'group',
    }
    results = derive_match_probabilities({}, mock_markets, mock_research)
    assert len(results) == 6
    assert all(1 <= r['p'] <= 99 for r in results)
    print(f"  derive_match_probabilities (6 markets) → all 1–99 ✓")
    for r in results:
        print(f"    {r['archetype']:<16} p={r['p']:>2}  {r['opportunity']:<8}  {r['driver'][:45]}")

    print("\n── All self-tests passed ──")

    # ── Session flow reference ────────────────────────────────────
    print(f"""
SESSION FLOW (§3 autonomous loop) — {now_ist()}
─────────────────────────────────────────────────────
STEP 1  SYNC
  mcp__SportsPredict__list_matches(event_id="{EVENT_ID}")
  mcp__SportsPredict__list_predictions(lobby_id="{LOBBY_ID}")
  mcp__SportsPredict__list_results(lobby_id="{LOBBY_ID}")

STEP 2  TRIAGE
  build_triage_table(matches, predictions, markets_by_match)
  → deadline table in IST, coverage states, horizon classification

STEP 3  SETTLE AUDIT (if new results)
  decode_all(results) → decode_outcome() for each
  run band_decomposition() and per_match_brier() if n > 50 new

STEP 4  DEPTH PASS (near horizon <48h, primary)
  For each near match:
    list_markets(match_id=...)
    [web research: 6–10 lookups per §6.3]
    derive_match_probabilities(match, markets, research)
    if should_run_mc(results): batch_mc([build_mc_input(...)])
    submit_predictions_batch (≤50/call) for new markets
    update_prediction for abs(Δ) ≥ 3 markets

STEP 5  COVERAGE SWEEP (mid/far, secondary, 12–16 matches)
  For each UNCOVERED/PARTIAL match in mid/far horizon:
    list_markets(match_id=...)
    [cluster anchor harvesting: 2–4 lookups per §6.1]
    derive_match_probabilities → submit_predictions_batch

STEP 6  REPORT
  status_block(...) + after_action_report(per match)
  + rbp_scoreboard(if crowd_brier available)

Key constants:
  EVENT_ID = {EVENT_ID}
  LOBBY_ID = {LOBBY_ID}
  Rate limit: 60 req/min/IP — batch writes, pace sweeps
  Deadline = opening_time (kickoff) — hard lock D7
""")


if __name__ == '__main__':
    main()
