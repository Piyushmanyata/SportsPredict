"""§5.4 — tie-trap engine for strict "Team A more X than Team B" markets."""
from .utils import poisson_pmf

# §5.4 reference table (mean m, tie %, even-matchup "A more" %) — kept for
# citation; tie_probability()/split_more() below compute the exact values.
REFERENCE_STATS = {
    "fouls": {"m": 11, "tie_pct": 8.6, "even_a_more_pct": 46},
    "ft_corners": {"m": 4.5, "tie_pct": 13.5, "even_a_more_pct": 43},
    "2h_corners": {"m": 2.4, "tie_pct": 18.8, "even_a_more_pct": 41},
    "ht_corners": {"m": 2.1, "tie_pct": 20.2, "even_a_more_pct": 40},
    "2h_sot": {"m": 2.0, "tie_pct": 20.7, "even_a_more_pct": 40},
    "cards": {"m": 1.8, "tie_pct": 21.9, "even_a_more_pct": 39},
    "offsides": {"m": 1.5, "tie_pct": 24.3, "even_a_more_pct": 38},
}

# L9-adjacent skew guidance (§5.4): dominant side's conditional split.
FAVORED_SIDE_RANGE = (44, 52)
WEAK_SIDE_RANGE = (27, 36)


def tie_probability(m, kmax=80):
    """Exact tie mass for two independent Poisson(m): sum_k pmf(k,m)^2."""
    return sum(poisson_pmf(k, m) ** 2 for k in range(kmax))


def p_more(mA, mB, kmax=80):
    """P(A more), P(tie), P(B more) for independent Poisson(mA), Poisson(mB)."""
    pmf_a = [poisson_pmf(k, mA) for k in range(kmax)]
    pmf_b = [poisson_pmf(k, mB) for k in range(kmax)]
    cum_b = [0.0]
    for x in pmf_b:
        cum_b.append(cum_b[-1] + x)
    cum_a = [0.0]
    for x in pmf_a:
        cum_a.append(cum_a[-1] + x)
    tie = sum(a * b for a, b in zip(pmf_a, pmf_b))
    a_more = sum(pmf_a[k] * cum_b[k] for k in range(kmax))
    b_more = sum(pmf_b[k] * cum_a[k] for k in range(kmax))
    return a_more, tie, b_more


def enforce_never_50(p):
    """§5.4: 'Never hand 50 to a strict comparison.'"""
    if p == 50:
        raise ValueError("strict comparison markets may never be submitted at exactly 50 (§5.4)")
    return p
