"""
Situational overlays (§5.12).

Each overlay returns a signed integer delta (pts), capped so the
TOTAL across all overlays does not exceed ±8 pts per market.

Usage:
    delta = apply_overlays(overlays_list)
    final_p = clamp(base_p_int + delta, 1, 99)
"""

from dataclasses import dataclass, field


@dataclass
class OverlayConfig:
    """
    Container for per-match situational overlay inputs.
    All deltas are integers in the per-overlay range specified by §5.12.
    """

    # Must-win / dead rubber (verify; rarer in 12×4 + 8-thirds format)
    must_win_delta: int = 0         # typically +2 to +5 on win markets when must-win

    # MD3 rotation risk
    rotation_delta: int = 0         # −3 to −6 on favourite win; also slash player props

    # Rest gap ≥ 2 days advantage for one side
    rest_delta: int = 0             # ±1 to ±3

    # Altitude (§5.12 hardened v8)
    # Azteca ≈ 2,240 m: −2 to −4 on lowland favourite's win/scoring λ
    altitude_delta: int = 0

    # Winner's slump — reigning champion drag (§5.12 new v8, judgement call)
    # ±1 to −2 max, flag as soft overlay
    winners_slump_delta: int = 0

    # Weather: heavy rain/heat → Unders +2 to +3
    weather_unders_delta: int = 0

    # Travel + summer heat: afternoon North American kickoff → Unders +2 to +3
    travel_heat_delta: int = 0

    # Referee profile: strict ref → card markets ±up to ±8 total on card lines
    referee_cards_delta: int = 0    # card-specific markets only

    # Custom freeform overlay (with written driver)
    custom_delta: int = 0
    custom_note: str = ""

    @property
    def total(self) -> int:
        """Sum all overlays, capped at ±8 (§5.12)."""
        raw = (
            self.must_win_delta
            + self.rotation_delta
            + self.rest_delta
            + self.altitude_delta
            + self.winners_slump_delta
            + self.weather_unders_delta
            + self.travel_heat_delta
            + self.custom_delta
        )
        return max(-8, min(8, raw))

    def cards_total(self) -> int:
        """Total overlay for card-specific markets (adds referee delta)."""
        raw = self.total + self.referee_cards_delta
        return max(-8, min(8, raw))

    def describe(self) -> list[str]:
        """Human-readable list of active overlays with deltas."""
        lines = []
        if self.must_win_delta:
            lines.append(f"must-win scenario: {self.must_win_delta:+d}")
        if self.rotation_delta:
            lines.append(f"rotation (MD3/already-through): {self.rotation_delta:+d}")
        if self.rest_delta:
            lines.append(f"rest gap ≥2d advantage: {self.rest_delta:+d}")
        if self.altitude_delta:
            lines.append(f"altitude (Azteca/Guadalajara): {self.altitude_delta:+d}")
        if self.winners_slump_delta:
            lines.append(f"winner's-slump (soft judgement): {self.winners_slump_delta:+d}")
        if self.weather_unders_delta:
            lines.append(f"weather/heat → Unders: {self.weather_unders_delta:+d}")
        if self.travel_heat_delta:
            lines.append(f"travel/heat/afternoon KO: {self.travel_heat_delta:+d}")
        if self.referee_cards_delta:
            lines.append(f"referee profile (card markets only): {self.referee_cards_delta:+d}")
        if self.custom_delta:
            lines.append(f"custom overlay ({self.custom_note}): {self.custom_delta:+d}")
        lines.append(f"TOTAL (capped ±8): {self.total:+d}")
        return lines


def apply_overlays(
    base_p_int: int,
    config: OverlayConfig,
    market_type: str = "default",
) -> int:
    """
    Apply situational overlays to a base integer probability.

    Parameters
    ----------
    base_p_int : int
        Base 1-99 integer probability from the engine.
    config : OverlayConfig
        Overlay configuration for the match.
    market_type : str
        'cards' to also include the referee_cards_delta; otherwise only total.

    Returns
    -------
    int : adjusted probability, clamped 1-99.
    """
    delta = config.cards_total() if market_type == "cards" else config.total
    return max(1, min(99, base_p_int + delta))


# ---------------------------------------------------------------------------
# Altitude helper: quick check for Mexican venues
# ---------------------------------------------------------------------------

ALTITUDE_VENUES = {
    "estadio azteca":    2240,
    "guadalajara":       1566,
    "monterrey":         538,   # below threshold
}


def altitude_delta(venue: str, team_is_lowland: bool = True) -> int:
    """
    Return overlay delta for altitude effect (§5.12).
    Only applies to lowland teams at high-altitude venues.
    Azteca ≈ −3, Guadalajara ≈ −2, others 0.
    """
    key = venue.lower().strip()
    altitude_m = ALTITUDE_VENUES.get(key, 0)
    if altitude_m < 1200 or not team_is_lowland:
        return 0
    if altitude_m >= 2000:
        return -3   # Azteca
    return -2       # Guadalajara range
