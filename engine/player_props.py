"""
Player-prop engine (§5.6, L7, L10).

L10 (ACTIVE): main-striker 1+SOT band lowered from 60-72 → 52-64.
Driver gate: any modeled probability in the top half of 56-70 requires
an explicit written driver; without it, regress to the lower band edge.

L7: discount rotation risk inside λ allocation, not via final output.
"""

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Band definitions from spec (§5.6, v8)
# ---------------------------------------------------------------------------

# Goal bands
GOAL_BANDS = {
    "star_striker":    (0.32, 0.45),
    "secondary":       (0.18, 0.28),
    "midfielder":      (0.08, 0.15),
}

# 1+SOT bands (v8/L10 corrected)
SOT_BANDS = {
    "main_striker":    (0.52, 0.64),   # was 0.60-0.72 in v7 — L10 ACTIVE correction
    "winger_am":       (0.42, 0.56),
}

# Score-or-assist multipliers over goal rate (§5.6)
SOA_MULTIPLIER = {
    "creator":  (1.5, 1.8),  # e.g. attacking mids, wide creators
    "pure_9":   (1.2, 1.4),  # pure strikers
}


@dataclass
class PlayerPropEngine:
    """
    Compute player-prop probabilities for a single player.

    Parameters
    ----------
    team_lam : float
        Team expected goals (full match).
    player_goal_share : float
        Player's proportion of team goals (e.g., 0.35 for a star striker).
    player_sot_share : float | None
        Player's proportion of team SOT. If None, estimated as 2.0 × goal_share.
    team_lam_sot : float | None
        Team expected SOT (FT). If None, estimated as 3.0 × team_lam.
    role : str
        'main_striker', 'winger_am', 'secondary', 'midfielder'.
    rotation_factor : float
        Between 0 (not playing) and 1 (certain starter). Applied to λ_player before
        deriving all downstream props (L7: discount in λ allocation, not final output).
    """

    team_lam: float
    player_goal_share: float
    player_sot_share: float | None = None
    team_lam_sot: float | None = None
    role: str = "main_striker"
    rotation_factor: float = 1.0

    def __post_init__(self):
        if self.team_lam_sot is None:
            self.team_lam_sot = max(1.0, self.team_lam * 3.0)
        if self.player_sot_share is None:
            self.player_sot_share = min(0.5, self.player_goal_share * 2.0)

        # Apply rotation to the player's λ allocation (L7: discount here, not on output)
        self._lam_player_goals = self.team_lam * self.player_goal_share * self.rotation_factor
        self._lam_player_sot   = self.team_lam_sot * self.player_sot_share * self.rotation_factor

    # ------------------------------------------------------------------
    # Anytime goal (§5.6)
    # ------------------------------------------------------------------
    def anytime_goal(self) -> float:
        """P(player scores ≥ 1 goal) = 1 − e^(−λ_player_goals)."""
        return 1 - math.exp(-self._lam_player_goals)

    def anytime_goal_int(self) -> int:
        return max(1, min(99, round(self.anytime_goal() * 100)))

    # ------------------------------------------------------------------
    # 1+ SOT (§5.6, L10 band-gated)
    # ------------------------------------------------------------------
    def sot_1plus(self, driver: str | None = None) -> float:
        """
        P(player ≥ 1 SOT) = 1 − e^(−λ_player_sot).
        L10 band check: if modeled p falls in top half of 56-70 (i.e. >63%),
        regress to lower band edge unless an explicit driver is provided.
        """
        p = 1 - math.exp(-self._lam_player_sot)
        p_int = round(p * 100)

        # L10 driver gate: top half of 56-70 band → need explicit driver
        if 63 < p_int <= 70 and driver is None:
            # Regress to lower band edge for this role
            lo, hi = SOT_BANDS.get(self.role, (0.42, 0.64))
            p = lo
        elif p_int > 70:
            # Outside band: cap at 70 without anchor (noisy register spirit)
            p = min(p, 0.70)

        return p

    def sot_1plus_int(self, driver: str | None = None) -> int:
        return max(1, min(99, round(self.sot_1plus(driver) * 100)))

    # ------------------------------------------------------------------
    # 1+ SOT in 2H (§5.6)
    # ------------------------------------------------------------------
    def sot_1plus_2h(self, driver: str | None = None) -> float:
        """P(player ≥ 1 SOT in 2H) ≈ FT SOT prop at 0.55 × λ_player_sot.
        Capped at FT SOT probability to preserve coherence (2H ⊆ FT)."""
        lam_2h = 0.55 * self._lam_player_sot
        p_2h = 1 - math.exp(-lam_2h)
        # Coherence: P(2H SOT) must be ≤ P(FT SOT)
        p_ft = self.sot_1plus(driver)
        return min(p_2h, p_ft)

    def sot_1plus_2h_int(self, driver: str | None = None) -> int:
        return max(1, min(99, round(self.sot_1plus_2h(driver) * 100)))

    # ------------------------------------------------------------------
    # Score or assist (§5.6)
    # ------------------------------------------------------------------
    def score_or_assist(self, multiplier: float | None = None) -> float:
        """
        P(score or assist). = goal_prob × multiplier (overlap-corrected).
        multiplier: 1.2-1.4 for pure 9s, 1.5-1.8 for creators.
        """
        if multiplier is None:
            lo, hi = SOA_MULTIPLIER.get(
                "creator" if self.role in ("winger_am",) else "pure_9"
            )
            multiplier = (lo + hi) / 2

        raw_goal = self.anytime_goal()
        p = raw_goal * multiplier
        # Clamp: cannot exceed 1 and should not exceed the band ceiling
        return max(0.01, min(0.99, p))

    def score_or_assist_int(self, multiplier: float | None = None) -> int:
        return max(1, min(99, round(self.score_or_assist(multiplier) * 100)))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def all_props(self, driver: str | None = None) -> dict[str, int]:
        return {
            "anytime_goal":       self.anytime_goal_int(),
            "sot_1plus":          self.sot_1plus_int(driver),
            "sot_1plus_2h":       self.sot_1plus_2h_int(driver),
            "score_or_assist":    self.score_or_assist_int(),
        }
