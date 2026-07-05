"""§5.6 — Player-prop engine (lineup-gated, L7/L10).

v8 bands (L10 ACTIVE input-side correction — the old 60–72 striker-SOT band
is RETIRED):
  anytime goal:  star striker 32–45 · secondary 18–28 · mid 8–15
  1+ SOT:        main striker 52–64 · winger/AM 42–56

Driver gate (L10): landing ANY modeled probability in the top half of 56–70
requires an explicit written driver (recent per-90 SOT rate, expected
service/shot volume, confirmed starter + heavy minutes). With no driver,
regress toward the lower band edge. `driver_gate()` enforces this.

L7: under rotation risk, discount the player's ALLOCATED SHARE of team λ
(input side), never the final output probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import SHARE_2H

BANDS = {
    "anytime_goal": {"star_striker": (0.32, 0.45), "secondary": (0.18, 0.28), "mid": (0.08, 0.15)},
    "sot_1plus": {"main_striker": (0.52, 0.64), "winger_am": (0.42, 0.56)},
}

# Score-or-assist multiplier on the goal prob (overlap-corrected)
SOA_MULT = {"creator": (1.5, 1.8), "pure_nine": (1.2, 1.4)}


def driver_gate(p: float, has_written_driver: bool,
                band_lo: float = 0.56, band_hi: float = 0.70) -> float:
    """L10 gate for ALL modeled markets: a p in the top half of [56,70] with no
    explicit written driver regresses to the band's lower half boundary."""
    top_half_lo = (band_lo + band_hi) / 2.0
    if band_lo <= p <= band_hi and p > top_half_lo and not has_written_driver:
        return top_half_lo
    return p


@dataclass
class PlayerProp:
    """One player's prop set, derived coherently from team λ (L7).

    team_lam:        team goal λ from the fitted MatchModel
    goal_share:      player's share of team goals (haircut LLM-intuition
                     inputs 10–20% per §5.10 before passing in)
    sot_lam:         player's FULL-match 1+SOT rate λ (per-90 SOT × minutes factor)
    rotation_factor: multiply INTO the allocation under rotation risk (L7) —
                     e.g. 0.8 for real rotation doubt, 1.0 once lineup confirms
    """
    name: str
    team_lam: float
    goal_share: float
    sot_lam: float
    rotation_factor: float = 1.0

    @property
    def lam_goal(self) -> float:
        return self.team_lam * self.goal_share * self.rotation_factor

    @property
    def lam_sot(self) -> float:
        return self.sot_lam * self.rotation_factor

    def p_anytime_goal(self) -> float:
        return 1.0 - math.exp(-self.lam_goal)

    def p_score_or_assist(self, role: str = "pure_nine") -> float:
        lo, hi = SOA_MULT[role]
        mult = (lo + hi) / 2.0
        return min(0.99, self.p_anytime_goal() * mult)

    def p_sot_1plus(self, has_written_driver: bool = False) -> float:
        return driver_gate(1.0 - math.exp(-self.lam_sot), has_written_driver)

    def p_sot_1plus_2h(self) -> float:
        """1+ SOT in 2H ≈ rate-share 0.55 on the SOT λ."""
        return 1.0 - math.exp(-SHARE_2H * self.lam_sot)

    def p_sot_2plus(self) -> float:
        lam = self.lam_sot
        return 1.0 - math.exp(-lam) * (1.0 + lam)
