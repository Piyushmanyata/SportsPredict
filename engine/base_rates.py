"""Live base-rate tracker: empirical Bayes (spec section 5.8).

Noisy-register markets (penalties, red cards, ...) are tracked with a
shrinkage estimator so a handful of tournament-specific observations
don't overreact against the VAR-era prior. k starts high (7) so the
prior dominates on tiny samples, then relaxes to 15 once each event type
has enough of its own data.
"""

import json
import os

DEFAULT_PRIORS = {
    "penalty_per_match": 0.36,
    "red_card_per_match": 0.06,
    "pen_or_red_per_match": 0.32,
    "match_cards_mean": 3.7,
    "goals_per_match_group": 2.55,
}

_DEFAULT_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "base_rate_tracker.json")


def eb_posterior(observed_count, prior_rate, n_matches, k):
    """Posterior rate = (observed_count + k*prior_rate) / (n_matches + k)."""
    return (observed_count + k * prior_rate) / (n_matches + k)


def stepwise_k(n_matches_total, event_specific_n=None):
    """k=7 early in the tournament or while an event type has <10 observations, else 15."""
    if n_matches_total < 30:
        return 7.0
    if event_specific_n is not None and event_specific_n < 10:
        return 7.0
    return 15.0


def load_tracker(path=None):
    """Load the tracker JSON, seeding fresh entries from DEFAULT_PRIORS if the file is absent."""
    path = path or _DEFAULT_STATE_PATH
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        quantity: {"prior": prior, "observed_count": 0, "n_matches": 0, "working_value": prior}
        for quantity, prior in DEFAULT_PRIORS.items()
    }


def save_tracker(tracker, path=None):
    """Persist the tracker dict to disk as JSON, creating the state directory if needed."""
    path = path or _DEFAULT_STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(tracker, f, indent=2)


def update_tracker(tracker, quantity, new_observed_count, new_n_matches):
    """Update one quantity's counts and recompute its EB working_value in place."""
    entry = tracker[quantity]
    entry["observed_count"] = new_observed_count
    entry["n_matches"] = new_n_matches
    k = stepwise_k(new_n_matches)
    entry["working_value"] = eb_posterior(new_observed_count, entry["prior"], new_n_matches, k)
    return tracker


if __name__ == "__main__":
    import tempfile

    posterior = eb_posterior(1, 0.36, 5, 7)
    assert abs(posterior - 0.29333) < 0.001
    print("check 1 (EB posterior matches spec's worked ~29% example) OK")

    assert stepwise_k(10) == 7.0
    assert stepwise_k(50) == 15.0
    assert stepwise_k(50, event_specific_n=5) == 7.0
    assert stepwise_k(50, event_specific_n=12) == 15.0
    print("check 2 (stepwise k) OK")

    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "base_rate_tracker.json")

    tracker = load_tracker(tmp_path)
    assert set(DEFAULT_PRIORS) <= set(tracker)
    assert all(tracker[q]["n_matches"] == 0 for q in DEFAULT_PRIORS)
    print("check 3 (load_tracker seeds defaults on missing file) OK")

    update_tracker(tracker, "penalty_per_match", 1, 5)
    assert abs(tracker["penalty_per_match"]["working_value"] - 0.29333) < 0.001
    print("check 4 (update_tracker matches EB formula) OK")

    save_tracker(tracker, tmp_path)
    reloaded = load_tracker(tmp_path)
    assert abs(reloaded["penalty_per_match"]["working_value"] - tracker["penalty_per_match"]["working_value"]) < 1e-9
    print("check 5 (save/load round-trip) OK")

    print("base_rates.py: all checks passed")
