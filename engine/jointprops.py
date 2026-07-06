"""Joint / sequence props (spec §5.7).

Never price a joint prop above either marginal. Joint props inherit ALL the
lambda-estimation risk of both marginals plus the dependence haircut — they
are disproportionately exposed to a match-level lambda misread (L8).
"""

from __future__ import annotations

import math


def p_scores_first(lam_team: float, t: float) -> float:
    """P(team scores first) ~ (lam/T) * (1 - e^(-T))."""
    return (lam_team / t) * (1.0 - math.exp(-t))


def joint(p1: float, p2: float, haircut_pts: float = 1.5,
          same_direction: bool = True) -> float:
    """Product of marginals with a small dependence haircut (1-2 pts).

    same_direction=True: A leads -> B chases -> slightly more open game (mild
    positive dependence; haircut still applied conservatively). Opposite-
    direction combos get the full haircut. Clamped to min(p1, p2).
    """
    h = (haircut_pts if same_direction else 2.0) / 100.0
    return max(0.0, min(p1, p2, p1 * p2 - h))
