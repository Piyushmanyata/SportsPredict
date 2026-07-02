"""Market taxonomy: the 12 live archetypes and which engine module handles each (spec section 5.3).

This is a lookup table, not a forced-uniform dispatcher -- the 12
archetypes take genuinely different inputs (a 1X2 needs two lambdas, a
player prop needs a player lambda share, a threshold count needs a team
rate and a k). Forcing them through one generic call signature would
hide more than it clarifies. Read the "wording" column against the
market's actual question text, then call the named function directly
(see run_match.py for a worked end-to-end example).
"""

ARCHETYPES = [
    {
        "id": 1,
        "wording": "Will X win the match?",
        "module": "lambda_engine",
        "function": "win_draw_loss",
        "notes": "Devigged 1X2 (power-corrected via devig.py). NO = draw + loss combined. "
                 "Knockout: check regulation-win vs advance wording. L12 ACTIVE: apply the "
                 "Dixon-Coles/overdispersion draw inflation (dixon_coles_overdispersion_tilt) "
                 "firmly in the 40-60 win band -- input-side only, never a win-probability floor.",
    },
    {
        "id": 2,
        "wording": "3 or more total goals / 2 or fewer total goals",
        "module": "lambda_engine",
        "function": "total_goals_from_over25, poisson_cdf",
        "notes": "Totals grid.",
    },
    {
        "id": 3,
        "wording": "Both teams score AND 3+ total goals",
        "module": "lambda_engine",
        "function": "btts_and_3plus",
        "notes": "= btts - p_1_1. Never multiply marginals (correlated).",
    },
    {
        "id": 4,
        "wording": "Will X score in the second half?",
        "module": "lambda_engine",
        "function": "team_scores_2h",
        "notes": "1 - exp(-0.55*lambda_X).",
    },
    {
        "id": 5,
        "wording": "Will X score at least 1 goal?",
        "module": "lambda_engine",
        "function": "team_scores",
        "notes": "1 - exp(-lambda_X).",
    },
    {
        "id": 6,
        "wording": "more fouls/cards/corners(FT,HT,2H)/SOT than [strict comparison]",
        "module": "tie_trap",
        "function": "tie_probability, p_a_more_even, skewed_split",
        "notes": "Never hand 50 to a strict comparison -- tie mass is a real, exactly computable well.",
    },
    {
        "id": 7,
        "wording": "2+ offsides / 4+ total cards / 2+ cards in 2H / 5+ corners / 2+ SOT / "
                   "4+ total SOT in 2H / 2+ total goals in 2H",
        "module": "thresholds",
        "function": "poisson_at_least, cards_ge4_total, cards_ge2_second_half, "
                    "team_corners_ge5, team_sot_ge2, team_offsides_ge2",
        "notes": "Exact Poisson tail P(N>=k).",
    },
    {
        "id": 8,
        "wording": "player anytime goal / score-or-assist / 1+ SOT / 1+ SOT in 2H",
        "module": "player_props",
        "function": "anytime_goal_prob, sot_prob, sot_2h_prob, score_or_assist_prob",
        "notes": "L10 ACTIVE: SOT bands corrected to SOT_BANDS_V8; requires_l10_driver_gate "
                 "gates anything in the top half of 56-70.",
    },
    {
        "id": 9,
        "wording": "At halftime, will the match be tied?",
        "module": "thresholds",
        "function": "ht_tied",
        "notes": "L9: do not exceed HT_TIED_CEILING (47) unless anchor-implied T < 2.2.",
    },
    {
        "id": 10,
        "wording": "At halftime, both teams >=1 SOT",
        "module": "thresholds",
        "function": "ht_both_teams_sot",
        "notes": "Product of two independent HT-scaled SOT Poissons.",
    },
    {
        "id": 11,
        "wording": "X scores first AND Y scores in 2H [joint/sequence]",
        "module": "joint_props",
        "function": "p_scores_first, joint_prob",
        "notes": "Inherits both marginals' lambda-estimation risk plus a dependence haircut. "
                 "Never price above either marginal.",
    },
    {
        "id": 12,
        "wording": "penalty awarded / red card / pen OR red [drama props]",
        "module": "base_rates",
        "function": "eb_posterior, load_tracker, update_tracker",
        "notes": "Noisy register (see coherence.clamp_noisy_register, confidence ceiling = LOW).",
    },
]


def find_archetype(archetype_id):
    """Look up one archetype entry by its spec-numbered id (1-12)."""
    for entry in ARCHETYPES:
        if entry["id"] == archetype_id:
            return entry
    raise KeyError(f"no archetype with id {archetype_id}")


if __name__ == "__main__":
    assert len(ARCHETYPES) == 12
    assert {a["id"] for a in ARCHETYPES} == set(range(1, 13))
    assert find_archetype(1)["module"] == "lambda_engine"
    print("taxonomy.py: all checks passed")
