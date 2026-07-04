"""§5.7 — joint / sequence props."""
import math

from .utils import clamp


def p_scores_first(lamA, T):
    return (lamA / T) * (1 - math.exp(-T))


def joint_prob(p_event_a, p_event_b_given_a, dependence_haircut_pts=1.5, cap_pct=None):
    """Multiply marginals, apply the small dependence haircut (§5.7), and
    never let the joint exceed either marginal."""
    raw_pct = p_event_a * p_event_b_given_a * 100
    adjusted = clamp(raw_pct - dependence_haircut_pts, 0, 100)
    ceiling_pct = min(p_event_a, p_event_b_given_a) * 100
    if cap_pct is not None:
        ceiling_pct = min(ceiling_pct, cap_pct)
    return min(adjusted, ceiling_pct)
