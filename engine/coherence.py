"""
Coherence gates — run before every batch submission (§5.11).
1. 1X2 triplet sums to 100 ±2.
2. O/U ladders are monotone.
3. Complements consistent (clean sheet vs opponent-scores).
4. Joint <= both marginals.
5. |final - anchor| > 10 requires written driver.
6. Noisy register clamped 15-85 unless anchored.
7. L8 correlation count.
"""

from typing import Dict, List, Optional, Tuple
from constants import NOISY_MARKETS, UPDATE_THRESHOLD_DEFAULT


class CoherenceError(Exception):
    pass


def check_1x2(p_home: int, p_draw: int, p_away: int, tol: int = 2) -> Tuple[bool, str]:
    """1X2 triplet must sum to 100 ± tol."""
    total = p_home + p_draw + p_away
    if abs(total - 100) <= tol:
        return True, ""
    return False, f"1X2 sum = {total}, expected 100 ±{tol}"


def check_ou_monotone(ou_lines: List[Tuple[float, int]]) -> Tuple[bool, str]:
    """
    O/U ladder must be monotone: higher line -> lower over probability.
    ou_lines: list of (line, p_over_int) sorted by line ascending.
    """
    for i in range(1, len(ou_lines)):
        if ou_lines[i][1] > ou_lines[i - 1][1]:
            return False, (f"O/U not monotone: line {ou_lines[i][0]} has "
                           f"higher over-prob {ou_lines[i][1]} than "
                           f"line {ou_lines[i-1][0]} ({ou_lines[i-1][1]})")
    return True, ""


def check_complements(p_clean_sheet: int, p_opponent_scores: int,
                      tol: int = 2) -> Tuple[bool, str]:
    """Clean sheet and opponent-scores must sum to 100 ±tol."""
    total = p_clean_sheet + p_opponent_scores
    if abs(total - 100) <= tol:
        return True, ""
    return False, f"Complement inconsistency: clean_sheet={p_clean_sheet}, opponent_scores={p_opponent_scores}, sum={total}"


def check_joint_le_marginals(p_joint: int, p_a: int, p_b: int) -> Tuple[bool, str]:
    """Joint probability must be <= both marginals."""
    if p_joint <= p_a and p_joint <= p_b:
        return True, ""
    return False, f"Joint {p_joint} > marginal(s) A={p_a} B={p_b}"


def check_anchor_deviation(final: int, anchor: int,
                            threshold: int = 10,
                            driver: Optional[str] = None) -> Tuple[bool, str]:
    """
    |final - anchor| > threshold requires a written concrete cause.
    Returns (ok, message).
    """
    delta = abs(final - anchor)
    if delta <= threshold:
        return True, ""
    if driver:
        return True, f"|Δ|={delta} > {threshold} — driver: {driver}"
    return False, (f"|Δ|={delta} > {threshold} and no driver provided. "
                   f"Regress to anchor or provide a concrete cause.")


def check_noisy_clamp(market_name: str, p_int: int,
                       anchored: bool = False) -> Tuple[int, str]:
    """
    Clamp noisy register markets to 15-85 unless anchored.
    Returns (clamped_p, note).
    """
    is_noisy = any(n.lower() in market_name.lower() for n in NOISY_MARKETS)
    if not is_noisy:
        return p_int, ""

    if anchored:
        return p_int, ""

    clamped = max(15, min(85, p_int))
    if clamped != p_int:
        return clamped, f"Noisy register clamped {p_int} -> {clamped} (15-85, unanchored)"
    return p_int, ""


def check_no_fifty(p_int: int, market_name: str = "") -> Tuple[bool, str]:
    """D3: avoid submitting exactly 50 — breaks outcome-decode telemetry."""
    if p_int == 50:
        return False, f"Exactly 50 on '{market_name}' — rarely the truth; breaks §9.2 decode. Nudge ±1."
    return True, ""


def check_coherence(markets: List[Dict]) -> Dict:
    """
    Run all coherence gates on a batch of markets.

    markets: list of dicts with keys:
      - market_id, name, p_int (proposed probability 1-99)
      - optional: anchor_p, driver, anchored (bool), p_complement_int
      - optional: joint_marginals = [p_a, p_b] for joint props

    Returns {
      "pass": bool,
      "errors": [str],
      "warnings": [str],
      "adjusted": {market_id: new_p_int}
    }
    """
    errors = []
    warnings = []
    adjusted = {}

    # Index by name for complement and 1X2 checks
    by_name = {m["name"]: m for m in markets}

    # 1. 1X2 triplet check
    home = by_name.get("will_home_win") or by_name.get("home_win")
    draw = by_name.get("draw") or by_name.get("will_draw")
    away = by_name.get("will_away_win") or by_name.get("away_win")
    if home and draw and away:
        ok, msg = check_1x2(home["p_int"], draw["p_int"], away["p_int"])
        if not ok:
            errors.append(f"1X2: {msg}")

    for m in markets:
        mid = m.get("market_id", m["name"])
        p = m["p_int"]
        name = m["name"]
        anchor = m.get("anchor_p")
        driver = m.get("driver")
        anchored = m.get("anchored", False)

        # 2. Anchor deviation gate
        if anchor is not None:
            ok, msg = check_anchor_deviation(p, anchor, driver=driver)
            if not ok:
                errors.append(f"[{name}] {msg}")
                # Regress halfway to anchor as a fix
                new_p = (p + anchor) // 2
                adjusted[mid] = new_p
                warnings.append(f"[{name}] Auto-regressed {p} -> {new_p} (no driver)")

        # 3. Noisy clamp
        clamped, note = check_noisy_clamp(name, p, anchored)
        if clamped != p:
            warnings.append(f"[{name}] {note}")
            adjusted[mid] = clamped

        # 4. No-50 check
        ok, msg = check_no_fifty(p, name)
        if not ok:
            warnings.append(f"[{name}] {msg}")

        # 5. Joint <= marginals
        marginals = m.get("joint_marginals")
        if marginals and len(marginals) == 2:
            ok, msg = check_joint_le_marginals(p, marginals[0], marginals[1])
            if not ok:
                errors.append(f"[{name}] {msg}")

        # 6. Complement check
        complement_name = m.get("complement")
        if complement_name and complement_name in by_name:
            comp_p = by_name[complement_name]["p_int"]
            ok, msg = check_complements(p, comp_p)
            if not ok:
                warnings.append(f"[{name} <-> {complement_name}] {msg}")

        # 7. Hard bounds
        if not 1 <= p <= 99:
            errors.append(f"[{name}] p={p} outside 1-99 (D3)")

    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "adjusted": adjusted,
    }


def count_correlated_axes(markets: List[Dict]) -> Dict:
    """
    Count markets by latent axis for L8 trigger.
    Returns {axis: count, ...} and flag if any axis > 4.
    """
    from collections import Counter
    axes = Counter(m.get("axis", "unknown") for m in markets)
    flag = any(v > 4 for v in axes.values())
    return {"counts": dict(axes), "l8_triggered": flag,
            "dominant_axis": axes.most_common(1)[0] if axes else None}
