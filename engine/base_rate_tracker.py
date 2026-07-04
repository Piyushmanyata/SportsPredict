"""§5.8 — live base-rate tracker (empirical Bayes)."""

# Working values per §5.8 table (update in place at every settle audit —
# these persist in this file per D10; live counts/n do not).
PRIORS = {
    "penalty_per_match": 0.34,
    "red_card_per_match": 0.06,
    "pen_or_red_per_match": 0.31,
    "match_cards_mean": 3.5,
    "goals_per_match_group": 2.55,
}

K_EARLY = 7
K_LATE = 15
K_SWITCH_MATCHES = 30
K_SWITCH_OBS = 10


def current_k(n_matches_total, n_obs_of_type):
    """Stepwise k (§5.8): k=7 for the first ~30 matches or until the specific
    event type has n>=10 observations, then escalate to k=15."""
    if n_matches_total < K_SWITCH_MATCHES or n_obs_of_type < K_SWITCH_OBS:
        return K_EARLY
    return K_LATE


def eb_posterior(observed_count, n_matches, prior, k=None):
    if k is None:
        k = current_k(n_matches, observed_count)
    return (observed_count + k * prior) / (n_matches + k)
