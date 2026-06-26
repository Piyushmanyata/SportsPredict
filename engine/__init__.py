"""
Probability Engine v3 — all sub-modules re-exported for convenience.
"""
from .devig import power_devig, multiplicative_devig, devig_3way
from .lambda_engine import ou25_to_T, fit_lambda_split, poisson_table, LambdaModel
from .markets import compute_all_markets
from .tie_trap import tie_trap_prob, MEAN_STATS
from .player_props import PlayerPropEngine
from .mc_engine import batch_mc, mc_single
from .base_rates import BaseRateTracker
from .overlays import apply_overlays

__all__ = [
    "power_devig", "multiplicative_devig", "devig_3way",
    "ou25_to_T", "fit_lambda_split", "poisson_table", "LambdaModel",
    "compute_all_markets",
    "tie_trap_prob", "MEAN_STATS",
    "PlayerPropEngine",
    "batch_mc", "mc_single",
    "BaseRateTracker",
    "apply_overlays",
]
