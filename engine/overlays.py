"""§5.12 — situational overlays: judgement calls, not data. Small, capped, logged."""
from .utils import clamp

OVERLAY_CAP = 8

# Documented reference ranges — apply manually per match, never auto-stack
# past the cap.
RANGES = {
    "rotation_md3_favorite_win": (-6, -3),
    "altitude_azteca_lowland_favorite": (-4, -2),
    "winners_slump_reigning_champion": (-2, -1),
}


def combine_overlays(overlay_points, cap=OVERLAY_CAP):
    """overlay_points: iterable of signed point adjustments already chosen
    per-overlay (§5.12) — this only enforces the total cap."""
    return clamp(sum(overlay_points), -cap, cap)
