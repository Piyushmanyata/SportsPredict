"""Probability Cup engine — reusable implementation of the v8 spec's math.

Modules map to spec sections (probability-cup-system-instructions-v8-final.md):

  devig        §5.1  multiplicative / power devig, anchor blending
  poisson      §5.2  λ engine: fit T from O/U 2.5, fit split to 1X2, closed forms,
                     Dixon–Coles / overdispersion tilt (§5.2.1), joint props (§5.7)
  tie_trap     §5.4  strict "A more X than B" with exact Poisson tie mass
  thresholds   §5.5  threshold-count tails, HT-tied Bessel, HT both-teams-SOT
  player_props §5.6  lineup-gated player prop engine (v8 bands, L7 λ-allocation)
  montecarlo   §5.11 L8 batched MC over λ-uncertainty for correlated baskets
  coherence    §5.11 pre-batch coherence gates + noisy-register clamp (§5.9)
  audit        §9    outcome decoding, self-expected Brier, band decomposition,
                     RBP scoreboard (§9.5/§9.6)
  constants    §4.3, §5.8, §5.9 verified IDs, base rates, registers, stage weights

All probabilities are 0–1 floats internally; use `to_submission()` to get the
integer 1–99 the platform expects (D3).
"""

from .constants import EVENT_ID, LOBBY_ID, STAGE_WEIGHTS
from .devig import devig_multiplicative, devig_power, blend_anchor
from .poisson import (
    fit_T_from_over25, fit_split_to_1x2, MatchModel,
    dixon_coles_tilt, p_scores_first_and_other_scores_2h,
)
from .tie_trap import p_strict_more, tie_mass
from .thresholds import p_at_least, ht_tied, ht_both_teams_sot
from .player_props import PlayerProp
from .montecarlo import batch_mc
from .coherence import run_gates, clamp_noisy, to_submission
from .audit import decode_outcome, settle_audit, rbp_scoreboard

__all__ = [
    "EVENT_ID", "LOBBY_ID", "STAGE_WEIGHTS",
    "devig_multiplicative", "devig_power", "blend_anchor",
    "fit_T_from_over25", "fit_split_to_1x2", "MatchModel",
    "dixon_coles_tilt", "p_scores_first_and_other_scores_2h",
    "p_strict_more", "tie_mass",
    "p_at_least", "ht_tied", "ht_both_teams_sot",
    "PlayerProp", "batch_mc",
    "run_gates", "clamp_noisy", "to_submission",
    "decode_outcome", "settle_audit", "rbp_scoreboard",
]
