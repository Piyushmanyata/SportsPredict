"""Quick sanity check: python3 -m engine.selftest"""
from . import (
    base_rate_tracker, coherence, devig, joint_props, lambda_engine,
    ledger, monte_carlo, outcome_decode, overlays, player_props, rbp,
    thresholds, tie_trap,
)


def check(label, cond):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    assert cond, label


def main():
    d = devig.devig([0.55, 0.30, 0.20])
    check("devig sums to 1", abs(sum(d["probs"]) - 1) < 1e-6)

    T = lambda_engine.fit_T_from_over25(0.46)
    check("fit_T_from_over25(0.46) ~= 2.5", abs(T - 2.5) < 0.05)

    split = lambda_engine.split_lambdas(2.7, 0.48)
    ph, pdraw, pa = lambda_engine.win_draw_away(*split)
    check("split_lambdas reproduces target home win", abs(ph - 0.48) < 0.01)
    check("1X2 sums to 1", abs(ph + pdraw + pa - 1) < 1e-6)

    check("p_btts_3plus <= p_btts", lambda_engine.p_btts_3plus(1.65, 1.05) <= lambda_engine.p_btts(1.65, 1.05))

    a_more, tie, b_more = tie_trap.p_more(11, 11)
    check("even fouls tie ~8.6%", abs(tie * 100 - 8.6) < 0.5)
    check("even fouls A-more ~46%", abs(a_more * 100 - 46) < 1.0)

    check("HT tied even T=2.5 ~44%", abs(thresholds.p_ht_tied(0.45 * 1.25, 0.45 * 1.25) * 100 - 44) < 2.0)

    check("SOT >=2 at lam=2.0 ~59%", abs(thresholds.p_at_least(2, 2.0) * 100 - 59) < 1.0)

    gated = player_props.apply_driver_gate(65, has_written_driver=False, band_lower_edge=52)
    check("driver gate regresses ungrounded 65 to 52", gated == 52)
    gated2 = player_props.apply_driver_gate(65, has_written_driver=True, band_lower_edge=52)
    check("driver gate leaves 65 with a stated driver", gated2 == 65)

    mc = monte_carlo.batch_mc([{
        "name": "TEST-MATCH", "lam_a": 1.5, "sigma_a": 0.2, "lam_b": 1.0, "sigma_b": 0.15,
        "markets": ["btts3plus", "p_2h_2plus", "clean_sheet_a", "scores_2h_a"],
    }], n_draws=500)
    check("batch_mc returns all requested markets", set(mc["TEST-MATCH"]) == {"btts3plus", "p_2h_2plus", "clean_sheet_a", "scores_2h_a"})

    check("gate_1x2_sum passes on 40/30/30", coherence.gate_1x2_sum(40, 30, 30))
    check("gate_1x2_sum fails on 40/30/20", not coherence.gate_1x2_sum(40, 30, 20))
    check("noisy clamp floors at 15", coherence.clamp_noisy_register(5) == 15)

    check("EB posterior between prior and observed rate", 0.34 < base_rate_tracker.eb_posterior(3, 5, 0.34) < 0.6)

    check("decode_outcome YES", outcome_decode.decode_outcome(0.7, (0.7 - 1) ** 2) == 1)
    check("decode_outcome NO", outcome_decode.decode_outcome(0.7, 0.7 ** 2) == 0)

    check("rbp positive when your_brier < crowd_brier", rbp.rbp_market(0.30, 0.18, 2) > 0)

    check("overlay cap enforced", overlays.combine_overlays([-4, -4, -4]) == -8)

    check("joint_prob <= both marginals", joint_props.joint_prob(0.4, 0.5) <= 40)

    check("ledger has 16 entries (L1-L15 + L2b)", len(ledger.LESSONS) == 16)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
