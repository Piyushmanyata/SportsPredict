"""
12 market archetype handlers (§5.3).
Read the wording every time — "more than" has a tie trap, "2 or more/at least" does not.
Each handler takes a LambdaEngine instance + supplementary data and returns int prob 1-99.
"""

import math
from typing import Optional, Dict, Any
from .lambda_engine import (
    LambdaEngine, poisson_tail, poisson_cdf,
    CARDS_TABLE, CORNERS_GE5, SOT_GE2, OFFSIDES_GE2,
    lookup_table,
)
from .tie_trap import p_strict_more, price_strict_comparison
from .player_props import price_sot_prop, price_goal_prop, price_score_or_assist


def _to_int(p: float, lo: int = 1, hi: int = 99) -> int:
    return max(lo, min(hi, int(round(p * 100))))


# --- Archetype handlers ---

def arch1_win(engine: LambdaEngine, side: str = "home",
              win_band_40_60: bool = False) -> int:
    """
    #1 "Will X win the match?" — devigged 1X2 (power-corrected).
    NO = draw + loss combined.
    v8 L12 ACTIVE: in 40-60 band apply hardened Dixon-Coles draw inflation.
    side: "home" | "away"
    win_band_40_60: True if this match is in the near-coinflip range (apply L12).
    """
    p = engine.win_a() if side == "home" else engine.win_b()
    # L12: in 40-60 win band, let draw breathe (more draw/upset mass)
    if win_band_40_60 and 0.35 <= p <= 0.65:
        # Pull slightly toward draw: reduce win probability by 1-3 pts
        # Hardened Dixon-Coles + overdispersion: ~-2pt typical
        p = max(0.01, p - 0.02)
    return _to_int(p)


def arch2_totals(engine: LambdaEngine, question: str = "3_or_more") -> int:
    """
    #2 "3 or more total goals" / "2 or fewer total goals".
    question: "3_or_more" | "2_or_fewer" | "over_N.5" | "under_N.5"
    """
    if question == "3_or_more":
        p = poisson_tail(engine.T, 3)
    elif question == "2_or_fewer":
        p = poisson_cdf(engine.T, 2)
    elif question.startswith("over_"):
        line = float(question.split("_")[1])
        p = engine.over(line)
    elif question.startswith("under_"):
        line = float(question.split("_")[1])
        p = engine.under(line)
    else:
        p = engine.over(2.5)
    return _to_int(p)


def arch3_btts_3plus(engine: LambdaEngine) -> int:
    """#3 "Both teams score AND 3+ total goals" = BTTS - P(1-1). Never multiply marginals."""
    return _to_int(engine.btts_and_3plus())


def arch4_score_2h(engine: LambdaEngine, side: str = "home") -> int:
    """#4 "Will X score in the second half?" = 1 - e^(-0.55*lam_X)."""
    return _to_int(engine.team_scores_2h(side="a" if side == "home" else "b"))


def arch5_score_ft(engine: LambdaEngine, side: str = "home") -> int:
    """#5 "Will X score at least 1 goal?" = 1 - e^(-lam_X)."""
    return _to_int(engine.team_scores(side="a" if side == "home" else "b"))


def arch6_strict_comparison(stat: str,
                              m_a: Optional[float] = None,
                              m_b: Optional[float] = None,
                              is_dominant_side_a: Optional[bool] = None) -> int:
    """
    #6 Strict comparisons: "more fouls/cards/corners(FT,HT,2H)/SOT than".
    Uses tie-trap engine §5.4. Never hands 50.
    """
    p = price_strict_comparison(stat, m_a, m_b, is_dominant_side_a)
    return p  # already int from price_strict_comparison


def arch7_threshold(stat: str, lam: float, threshold_label: str) -> int:
    """
    #7 Threshold counts: "2+ offsides", "4+ total cards", "2+ cards in 2H",
    "5+ corners", "2+ SOT", "4+ total SOT in 2H", "2+ total goals in 2H".
    stat: "offsides" | "cards_total" | "cards_2h" | "corners" | "sot" | "sot_2h_total" | "goals_2h"
    lam: relevant Poisson mean for the stat
    threshold_label: e.g. "ge2", "ge4", "ge5"
    """
    threshold_map = {"ge1": 1, "ge2": 2, "ge3": 3, "ge4": 4, "ge5": 5, "ge6": 6}
    k = threshold_map.get(threshold_label, 2)

    if stat == "offsides":
        p_int = lookup_table(OFFSIDES_GE2, lam)
        if k == 2:
            return p_int
        # Recalculate for other thresholds
        p = poisson_tail(lam, k)
        return _to_int(p)

    elif stat in ("cards_total", "cards"):
        entry = lookup_table(CARDS_TABLE, lam)
        if isinstance(entry, dict):
            if k == 4:
                return entry.get("ge4_total", _to_int(poisson_tail(lam, 4)))
            elif k == 2:
                return entry.get("ge2_2h", _to_int(poisson_tail(lam * 0.62, 2)))
        p = poisson_tail(lam, k)
        return _to_int(p)

    elif stat == "cards_2h":
        lam_2h = lam * 0.62
        if k == 2:
            p_int = lookup_table(CARDS_TABLE, lam)
            if isinstance(p_int, dict):
                return p_int.get("ge2_2h", _to_int(poisson_tail(lam_2h, 2)))
        p = poisson_tail(lam_2h, k)
        return _to_int(p)

    elif stat == "corners":
        if k == 5:
            return lookup_table(CORNERS_GE5, lam)
        p = poisson_tail(lam, k)
        return _to_int(p)

    elif stat == "sot":
        if k == 2:
            return lookup_table(SOT_GE2, lam)
        p = poisson_tail(lam, k)
        return _to_int(p)

    elif stat == "sot_2h_total":
        # "4+ total SOT in 2H" — total both teams' 2H SOT
        # Approximate: scale FT λ by 2H share (0.55) for total
        lam_2h = lam * 0.55
        p = poisson_tail(lam_2h, k)
        return _to_int(p)

    elif stat == "goals_2h":
        lam_2h = engine.T * 0.55 if hasattr(stat, 'T') else lam * 0.55
        p = poisson_tail(lam_2h, k)
        return _to_int(p)

    else:
        p = poisson_tail(lam, k)
        return _to_int(p)


def arch8_player_prop(prop_type: str, player_type: str,
                       lam_sot: float, lam_goal: float,
                       rotation_factor: float = 1.0,
                       sot_driver: Optional[str] = None,
                       period: str = "FT") -> int:
    """
    #8 Player props: anytime goal, score-or-assist, 1+ SOT, 1+ SOT in 2H.
    Returns integer 1-99.
    """
    if prop_type == "1plus_sot":
        res = price_sot_prop(player_type, lam_sot, rotation_factor, sot_driver, period)
        return res.p_int
    elif prop_type == "anytime_goal":
        lam_p = lam_goal * rotation_factor
        res = price_goal_prop(player_type, lam_p)
        return res.p_int
    elif prop_type == "score_or_assist":
        lam_p = lam_goal * rotation_factor
        res = price_goal_prop(player_type, lam_p)
        soa = price_score_or_assist(res.probability)
        return soa.p_int
    else:
        return 50  # unknown — log and flag


def arch9_ht_tied(engine: LambdaEngine) -> int:
    """#9 "At halftime, will the match be tied?" — Bessel table §5.5. L9 ceiling 47."""
    return _to_int(engine.ht_tied())


def arch10_ht_both_sot(lam_sot_a: float, lam_sot_b: float) -> int:
    """#10 "At halftime, both teams >= 1 SOT" — product of HT-SOT Poissons §5.5."""
    from .lambda_engine import p_team_scores
    la_ht = 0.45 * lam_sot_a
    lb_ht = 0.45 * lam_sot_b
    p = p_team_scores(la_ht) * p_team_scores(lb_ht)
    return _to_int(p)


def arch11_joint_sequence(lam_a: float, lam_b: float, T: float,
                           side_scores_first: str = "home") -> int:
    """
    #11 Joint/sequence: "X scores first AND Y scores in 2H".
    P(A first) ≈ (lam_A/T) * (1 - e^(-T)); multiply by P(B scores 2H).
    Apply -1 to -2 dependence haircut. Never price above either marginal.
    """
    from .lambda_engine import p_scores_2h
    import math

    if side_scores_first == "home":
        la = lam_a
        lb = lam_b
    else:
        la = lam_b
        lb = lam_a

    if T < 0.01:
        return 1

    p_a_first = (la / T) * (1.0 - math.exp(-T))
    p_b_scores_2h = p_scores_2h(lb)
    # Dependence haircut: if A leads, B chases -> mild positive dependence on B
    # Use -1pt haircut as documented
    p_joint = p_a_first * p_b_scores_2h * 0.98  # ~-2% dependence haircut
    p_joint = min(p_joint, p_a_first, p_b_scores_2h)  # can't exceed either marginal

    return _to_int(p_joint)


def arch12_drama(event_type: str, base_p: int,
                  anchored: bool = False,
                  eb_adjustment: int = 0) -> int:
    """
    #12 Drama: "penalty awarded", "red card", "pen OR red".
    Base rates + EB tracker (§5.8). Noisy register — clamp 15-85 unless anchored.
    event_type: "penalty" | "red_card" | "pen_or_red"
    base_p: integer prior (e.g. 29 for penalty)
    eb_adjustment: empirical Bayes posterior adjustment (can be +/-)
    """
    p = base_p + eb_adjustment
    if not anchored:
        p = max(15, min(85, p))
    return max(1, min(99, p))


def price_market(market_name: str, archetype: int,
                  engine: Optional[LambdaEngine] = None,
                  extras: Optional[Dict[str, Any]] = None) -> Dict:
    """
    Route a market to its archetype handler.

    market_name: verbatim market wording.
    archetype: int 1-12.
    engine: LambdaEngine instance.
    extras: additional parameters required by some archetypes.

    Returns {p_int, archetype, mode, driver_note}.
    """
    extras = extras or {}
    result = {"archetype": archetype, "market_name": market_name}

    if archetype == 1:
        side = extras.get("side", "home")
        band = extras.get("win_band_40_60", False)
        result["p_int"] = arch1_win(engine, side, band)
        result["mode"] = "ANCHORED"

    elif archetype == 2:
        q = extras.get("question", "3_or_more")
        result["p_int"] = arch2_totals(engine, q)
        result["mode"] = "ANCHORED"

    elif archetype == 3:
        result["p_int"] = arch3_btts_3plus(engine)
        result["mode"] = "ANCHORED"

    elif archetype == 4:
        side = extras.get("side", "home")
        result["p_int"] = arch4_score_2h(engine, side)
        result["mode"] = "MODELED"

    elif archetype == 5:
        side = extras.get("side", "home")
        result["p_int"] = arch5_score_ft(engine, side)
        result["mode"] = "ANCHORED"

    elif archetype == 6:
        stat = extras.get("stat", "fouls")
        m_a = extras.get("m_a")
        m_b = extras.get("m_b")
        dominant = extras.get("is_dominant_side_a")
        result["p_int"] = arch6_strict_comparison(stat, m_a, m_b, dominant)
        result["mode"] = "MODELED"

    elif archetype == 7:
        stat = extras.get("stat", "corners")
        lam = extras.get("lam", 4.5)
        threshold = extras.get("threshold", "ge2")
        result["p_int"] = arch7_threshold(stat, lam, threshold)
        result["mode"] = "MODELED"

    elif archetype == 8:
        prop_type = extras.get("prop_type", "1plus_sot")
        player_type = extras.get("player_type", "main_striker")
        lam_sot = extras.get("lam_sot", 2.5)
        lam_goal = extras.get("lam_goal", 0.4)
        rotation = extras.get("rotation_factor", 1.0)
        driver = extras.get("sot_driver")
        period = extras.get("period", "FT")
        result["p_int"] = arch8_player_prop(prop_type, player_type,
                                             lam_sot, lam_goal,
                                             rotation, driver, period)
        result["mode"] = "MODELED"

    elif archetype == 9:
        result["p_int"] = arch9_ht_tied(engine)
        result["mode"] = "MODELED"

    elif archetype == 10:
        lam_sot_a = extras.get("lam_sot_a", 3.0)
        lam_sot_b = extras.get("lam_sot_b", 3.0)
        result["p_int"] = arch10_ht_both_sot(lam_sot_a, lam_sot_b)
        result["mode"] = "MODELED"

    elif archetype == 11:
        lam_a = engine.lam_a if engine else extras.get("lam_a", 1.35)
        lam_b = engine.lam_b if engine else extras.get("lam_b", 1.35)
        T = engine.T if engine else (lam_a + lam_b)
        side = extras.get("side_scores_first", "home")
        result["p_int"] = arch11_joint_sequence(lam_a, lam_b, T, side)
        result["mode"] = "MODELED"

    elif archetype == 12:
        event_type = extras.get("event_type", "penalty")
        base_p = extras.get("base_p", 29)
        anchored = extras.get("anchored", False)
        eb_adj = extras.get("eb_adjustment", 0)
        result["p_int"] = arch12_drama(event_type, base_p, anchored, eb_adj)
        result["mode"] = "MODELED"

    else:
        result["p_int"] = 50
        result["mode"] = "UNKNOWN"

    return result
