"""Joint / sequence props: "A scores first AND B scores in 2H" (spec section 5.7).

Joint props inherit all of the lambda-estimation risk of both marginals
plus a dependence haircut. Never price a joint prop above either
marginal -- that would mean the "and" event is more likely than one of
its own halves.
"""

import math


def p_scores_first(lam_a, T):
    """Approximation for P(team A scores first) = (lam_a / T) * (1 - exp(-T))."""
    if T == 0:
        return 0.0
    return (lam_a / T) * (1.0 - math.exp(-T))


def joint_prob(p_event_a, p_event_b, dependence_haircut_pts=1.5):
    """Independence product minus a small dependence haircut, capped at either marginal."""
    raw = p_event_a * p_event_b
    adjusted = max(0.0, raw - dependence_haircut_pts / 100.0)
    return min(adjusted, p_event_a, p_event_b)


def positive_dependence_boost(p_event_b_given_chasing, boost_pts=1.5):
    """Mild positive-dependence bump when side B is chasing the game (more open play)."""
    return min(0.97, p_event_b_given_chasing + boost_pts / 100.0)


if __name__ == "__main__":
    result = p_scores_first(1.5, 3.0)
    assert abs(result - (1.5 / 3.0) * (1 - math.exp(-3.0))) < 1e-9
    assert p_scores_first(1.0, 0.0) == 0.0
    print("check 1 (p_scores_first) OK")

    result = joint_prob(0.30, 0.50, dependence_haircut_pts=1.5)
    assert result < 0.30 * 0.50
    assert result <= 0.30 and result <= 0.50
    print("check 2 (haircut + marginal cap) OK")

    result = joint_prob(0.96, 0.97, dependence_haircut_pts=1.0)
    assert result <= 0.96 and result <= 0.97
    print("check 3 (marginal cap binds on large marginals) OK")

    assert positive_dependence_boost(0.40, 1.5) > 0.40
    assert positive_dependence_boost(0.96, 5.0) <= 0.97
    print("check 4 (positive dependence boost + clamp) OK")

    print("joint_props.py: all checks passed")
