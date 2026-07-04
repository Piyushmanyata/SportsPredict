"""§5.11 — coherence gates + correlation cap. Run before every batch submit."""
from .utils import clamp

NOISY_MARKETS = {
    "penalty_awarded", "red_card", "pen_or_red", "2h_cards",
    "ht_sot_comparison", "2h_sot_comparison", "offside_count",
    "ht_corner_comparison", "2h_corner_comparison", "leads_at_ht",
}


def gate_1x2_sum(p_home, p_draw, p_away, tol=2):
    return abs((p_home + p_draw + p_away) - 100) <= tol


def gate_ou_monotone(over_probs_ascending_threshold):
    """P(Over X) must be non-increasing as the threshold X rises."""
    pairs = zip(over_probs_ascending_threshold, over_probs_ascending_threshold[1:])
    return all(a >= b for a, b in pairs)


def gate_complement(p_clean_sheet_a, p_b_scores, tol=2):
    """Clean sheet for A <=> B doesn't score."""
    return abs((p_clean_sheet_a + p_b_scores) - 100) <= tol


def gate_joint_le_marginals(p_joint, p_marginal_a, p_marginal_b):
    return p_joint <= min(p_marginal_a, p_marginal_b)


def gate_anchor_deviation(final_p, anchor_p, max_dev=10):
    """False => needs a written concrete cause, else regress to anchor (§5.11.2)."""
    return abs(final_p - anchor_p) <= max_dev


def clamp_noisy_register(p, floor=15, ceil=85, anchored=False):
    return p if anchored else clamp(p, floor, ceil)


def flag_correlation_axis(market_count_on_axis, total_markets=10, threshold=4):
    """L8: >4 of ~10 markets sharing a latent axis -> route to batched MC."""
    return market_count_on_axis > threshold
