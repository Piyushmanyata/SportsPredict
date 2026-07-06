"""§5.4 tie-trap engine: strict "Team A more X than Team B" markets.

P(A more) = (1 - P(tie)) * P(A more | no tie)
Never hand 50 to a strict comparison -- the crowd's tie-blind 50 is the
richest well (L3, CONFIRMED n=32 @118).
"""
from .poisson import poisson_tie_prob, poisson_greater_prob

REFERENCE_TABLE = {
    # stat -> (per-team mean m, exact tie %, even-matchup "A more" %)
    "fouls": (11, 8.6, 46),
    "ft_corners": (4.5, 13.5, 43),
    "2h_corners": (2.4, 18.8, 41),
    "ht_corners": (2.1, 20.2, 40),
    "2h_sot": (2.0, 20.7, 40),
    "cards": (1.8, 21.9, 39),
    "offsides": (1.5, 24.3, 38),
}


def tie_prob(m_a, m_b=None):
    """Exact tie mass for two Poisson means (equal means if m_b omitted)."""
    return poisson_tie_prob(m_a, m_a if m_b is None else m_b)


def p_a_more(m_a, m_b):
    """Exact P(A's count > B's count) for independent Poisson(m_a), (m_b).

    For an even matchup (m_a == m_b) this reproduces REFERENCE_TABLE's
    "even-matchup A more" column via (1-tie)/2.
    """
    return poisson_greater_prob(m_a, m_b)


def skewed_split(m_dominant, m_weak):
    """Favored side ~44-52, weak side ~27-36 per the strength-skew note.
    Returns the exact (dominant_more, weak_more, tie) rather than the
    hand-rounded reference bands -- use this for any non-even matchup.
    """
    tie = tie_prob(m_dominant, m_weak)
    dominant_more = p_a_more(m_dominant, m_weak)
    weak_more = p_a_more(m_weak, m_dominant)
    return {"dominant_more": dominant_more, "weak_more": weak_more, "tie": tie}
