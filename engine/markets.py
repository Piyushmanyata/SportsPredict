"""Market pricing sheet + question router (spec §5.3, §5.5-§5.7, §5.9).

Turns anchors into a per-match pricing context, then routes the live market
question text (as returned by ``list_markets``) to the right engine formula.
This replaces per-session re-derivation: one ``MatchContext.from_anchors`` +
one ``price_question`` per market covers the whole recurring inventory.

    ctx = MatchContext.from_anchors("POR", "ESP",
                                    odds_1x2=[4.10, 3.60, 1.87],
                                    odds_ou25=[2.00, 1.8333],
                                    odds_advance=[2.80, 1.4444])
    p = price_question("Will Spain advance to the quarterfinals?", ctx)

Per D4, unrecognised questions return a labeled base-rate fallback when one
exists and ``None`` otherwise (caller must then price by hand — never skip).
Noisy-register outputs are clamped 15-85 (§5.9) unless anchored.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from engine.constants import STAT_MEANS, SECOND_HALF_GOAL_SHARE, SECOND_HALF_CARD_SHARE
from engine.devig import devig
from engine.goals import (
    fit_split, one_x_two, p_btts, p_btts_and_3plus, p_clean_sheet_a,
    p_scores, p_scores_1h, p_scores_2h, p_total_goals_geq, pois_pmf, pois_sf,
    t_from_over25,
)
from engine.jointprops import p_scores_first
from engine.players import p_anytime_goal, p_score_or_assist, p_sot_1plus
from engine.thresholds import p_geq, p_ht_tied
from engine.tietrap import p_more_exact

# 48-team code <-> question-text name map (2026 WC field, as seen in live
# market text; extend on sight of a new code).
TEAM_NAMES = {
    "ALG": "algeria", "ARG": "argentina", "AUS": "australia", "AUT": "austria",
    "BEL": "belgium", "BIH": "bosnia", "BRA": "brazil", "CAN": "canada",
    "CIV": "ivory coast", "COD": "dr congo", "COL": "colombia",
    "CPV": "cape verde", "CRC": "costa rica", "CRO": "croatia",
    "CUW": "curaçao", "CZE": "czechia", "ECU": "ecuador", "EGY": "egypt",
    "ENG": "england", "ESP": "spain", "FRA": "france", "GER": "germany",
    "GHA": "ghana", "HAI": "haiti", "IRN": "iran", "IRQ": "iraq",
    "ITA": "italy", "JAM": "jamaica", "JOR": "jordan", "JPN": "japan",
    "KOR": "korea", "KSA": "saudi arabia", "MAR": "morocco", "MEX": "mexico",
    "NED": "netherlands", "NOR": "norway", "NZL": "new zealand",
    "PAN": "panama", "PAR": "paraguay", "POR": "portugal", "QAT": "qatar",
    "RSA": "south africa", "SCO": "scotland", "SEN": "senegal",
    "SUI": "switzerland", "SWE": "sweden", "TUN": "tunisia",
    "TUR": "türkiye", "URU": "uruguay", "USA": "united states",
    "UZB": "uzbekistan",
}

# D4 labeled base-rate fallbacks for exotic one-off props (working values —
# refresh from settle audits). Keys are lowercase substrings of the question.
EXOTIC_BASE_RATES = {
    "own goal be scored": 9,
    "header goal": 42,
    "goal be scored from outside the penalty area": 30,
    "goal be scored in first-half stoppage": 20,
    "goal be scored in second-half stoppage": 33,
    "substitute score a goal": 31,
    "substitution be made before halftime": 22,
    "9 or more total substitutions": 55,
    "goal be scored before the first hydration break": 45,
    "goal be scored after the second hydration break": 62,
    "card be shown after the second hydration break": 74,
    "either team be ruled offside before the first hydration break": 58,
    "first card of the match be shown before the first goal": 45,
    "any player score 2 or more goals": 18,
    "any player score more than 1 goal": 18,
}

_NOISY_HINTS = (
    "penalty", "red card", "offside", "stoppage", "hydration",
    "card be shown", "cards", "first card",
)


@dataclass
class PlayerCtx:
    """Per-player pricing inputs. goal_share is the share of the team's
    goals while on the pitch; minutes is the expected fraction played."""
    team: str                  # "a" or "b"
    goal_share: float = 0.20
    sot_lam: float = 0.8       # expected personal SOT over the full match
    minutes: float = 1.0       # L7 rotation discount lives HERE, not on output
    role: str = "creator"      # for score-or-assist uplift
    is_gk: bool = False


@dataclass
class MatchContext:
    code_a: str
    code_b: str
    lam_a: float
    lam_b: float
    # devigged anchors (0-1), optional
    p1x2: tuple[float, float, float] | None = None       # (a, draw, b)
    p_adv_a: float | None = None
    # per-team count-stat lambdas (full match)
    sot_a: float = 4.3
    sot_b: float = 4.3
    corners_a: float = 4.8
    corners_b: float = 4.8
    cards_a: float = 1.9
    cards_b: float = 1.9
    offsides_a: float = 1.8
    offsides_b: float = 1.8
    fouls_a: float = STAT_MEANS["fouls"]
    fouls_b: float = STAT_MEANS["fouls"]
    shots_a: float = 12.0
    shots_b: float = 12.0
    players: dict[str, PlayerCtx] = field(default_factory=dict)

    @property
    def t(self) -> float:
        return self.lam_a + self.lam_b

    @property
    def name_a(self) -> str:
        return TEAM_NAMES.get(self.code_a, self.code_a.lower())

    @property
    def name_b(self) -> str:
        return TEAM_NAMES.get(self.code_b, self.code_b.lower())

    @classmethod
    def from_anchors(cls, code_a: str, code_b: str,
                     odds_1x2: list[float] | None = None,
                     odds_ou25: list[float] | None = None,
                     p1x2: tuple[float, float, float] | None = None,
                     over25: float | None = None,
                     odds_advance: list[float] | None = None,
                     **stat_overrides) -> "MatchContext":
        """Build a context from decimal odds ([a, draw, b], [over, under],
        [adv_a, adv_b]) or pre-devigged probabilities."""
        if odds_1x2 is not None:
            p1x2 = tuple(devig(odds_1x2)["probs"])
        if odds_ou25 is not None:
            over25 = devig(odds_ou25)["probs"][0]
        if p1x2 is None or over25 is None:
            raise ValueError("need 1X2 and O/U 2.5 anchors (odds or probs)")
        t = t_from_over25(over25)
        lam_a, lam_b = fit_split(t, p1x2[0])
        p_adv_a = None
        if odds_advance is not None:
            p_adv_a = devig(odds_advance)["probs"][0]
        return cls(code_a=code_a, code_b=code_b, lam_a=lam_a, lam_b=lam_b,
                   p1x2=p1x2, p_adv_a=p_adv_a, **stat_overrides)

    # -- derived quantities ------------------------------------------------
    def reg_1x2(self) -> tuple[float, float, float]:
        """(win_a, draw, win_b): anchor if present, else Poisson closed form."""
        return self.p1x2 if self.p1x2 else one_x_two(self.lam_a, self.lam_b)

    def advance(self, side: str, et_edge: float = 0.5) -> float:
        """P(side advances) = reg win + draw x ET/pens share (default even)."""
        if side == "a" and self.p_adv_a is not None:
            return self.p_adv_a
        if side == "b" and self.p_adv_a is not None:
            return 1.0 - self.p_adv_a
        wa, d, wb = self.reg_1x2()
        return (wa + d * et_edge) if side == "a" else (wb + d * (1 - et_edge))


def _pct(p: float) -> int:
    """Probability -> D3-legal integer (1-99, never exactly 50)."""
    v = int(round(100 * p)) if p <= 1 else int(round(p))
    v = max(1, min(99, v))
    return 51 if v == 50 else v


def _clamp_noisy(v: int) -> int:
    return max(15, min(85, v))


def _half_lams(lam: float) -> tuple[float, float]:
    return (1 - SECOND_HALF_GOAL_SHARE) * lam, SECOND_HALF_GOAL_SHARE * lam


def _same_goals_both_halves(t: float) -> float:
    l1, l2 = _half_lams(t)
    return sum(pois_pmf(k, l1) * pois_pmf(k, l2) for k in range(10))


def _second_half_more_goals(t: float) -> float:
    l1, l2 = _half_lams(t)
    p = 0.0
    for k2 in range(1, 11):
        p += pois_pmf(k2, l2) * sum(pois_pmf(k1, l1) for k1 in range(k2))
    return p


def _find_player(q: str, ctx: MatchContext) -> tuple[str, PlayerCtx] | None:
    for name, pc in ctx.players.items():
        if name.lower() in q:
            return name, pc
    return None


def _team_side(q: str, ctx: MatchContext) -> str | None:
    """Which team the question refers to; None if neither/ambiguous-both."""
    a, b = ctx.name_a in q, ctx.name_b in q
    if a and not b:
        return "a"
    if b and not a:
        return "b"
    return None


def _cmp_sides(q: str, marker: str, ctx: MatchContext) -> tuple[str, str] | None:
    """For 'X more <stat> than Y' questions: (subject, object) sides."""
    head = q.split(marker)[0]
    if ctx.name_a in head and ctx.name_b not in head:
        return "a", "b"
    if ctx.name_b in head and ctx.name_a not in head:
        return "b", "a"
    return None


def price_question(question: str, ctx: MatchContext) -> tuple[int, str] | None:
    """Route one live market question to a price. Returns (p, label) or None.

    Label records the pricing path for the session log; "FALLBACK" labels are
    D4 base rates and must be reported as such.
    """
    q = question.lower()
    la, lb, t = ctx.lam_a, ctx.lam_b, ctx.t
    stat = {
        "a": {"sot": ctx.sot_a, "corner": ctx.corners_a, "card": ctx.cards_a,
              "offside": ctx.offsides_a, "foul": ctx.fouls_a, "shot": ctx.shots_a,
              "goal": la},
        "b": {"sot": ctx.sot_b, "corner": ctx.corners_b, "card": ctx.cards_b,
              "offside": ctx.offsides_b, "foul": ctx.fouls_b, "shot": ctx.shots_b,
              "goal": lb},
    }

    def k_of(pattern: str) -> int | None:
        m = re.search(pattern, q)
        return int(m.group(1)) if m else None

    # ---- player props first (guard against team-name substrings) ----------
    hit = _find_player(q, ctx)
    if hit:
        _, pc = hit
        team_lam = la if pc.team == "a" else lb
        if pc.is_gk and (k := k_of(r"(\d+) or more saves")) is not None:
            opp_sot = ctx.sot_b if pc.team == "a" else ctx.sot_a
            opp_lam = lb if pc.team == "a" else la
            return _pct(pois_sf(k, max(0.5, opp_sot - opp_lam))), "gk-saves"
        if "score or assist" in q:
            pg = p_anytime_goal(team_lam * pc.goal_share * pc.minutes)
            return _pct(p_score_or_assist(pg, pc.role)), "player-soa"
        if "score a goal" in q or ("score" in q and "goal" in q):
            return _pct(p_anytime_goal(team_lam * pc.goal_share * pc.minutes)), "player-goal"
        k = k_of(r"(\d+) or more shots on target") or k_of(r"at least (\d+) shots? on target")
        if k is not None:
            lam_sot = pc.sot_lam * pc.minutes
            if "second half" in q:
                lam_sot *= 0.55
            p = p_sot_1plus(lam_sot) if k == 1 else pois_sf(k, lam_sot)
            return _pct(p), "player-sot"
        if "play the entire match" in q:
            return _pct(0.42 if pc.minutes >= 0.95 else 0.15), "player-minutes"

    # ---- advance / win ----------------------------------------------------
    if "advance" in q:
        side = _team_side(q, ctx)
        if side:
            return _pct(ctx.advance(side)), "advance"
    if re.search(r"win (the match|in regulation)", q) or "win by" in q:
        side = _team_side(q, ctx)
        if side:
            wa, d, wb = ctx.reg_1x2()
            if (k := k_of(r"win by (\d+) or more")) is not None and k >= 2:
                lam_s, lam_o = (la, lb) if side == "a" else (lb, la)
                p = sum(pois_pmf(gs, lam_s) * sum(pois_pmf(go, lam_o)
                        for go in range(max(0, gs - k + 1)))
                        for gs in range(k, 12))
                return _pct(p), "win-by-k"
            return _pct(wa if side == "a" else wb), "1x2"
    if "end in a tie" in q or "extra time" in q:
        return _pct(ctx.reg_1x2()[1]), "reg-draw"

    # ---- goals: totals, BTTS, halves ---------------------------------------
    if "both teams score" in q:
        if (k := k_of(r"(\d+) or more total goals")) is not None:
            return _pct(p_btts_and_3plus(la, lb)), "btts+3"
        return _pct(p_btts(la, lb)), "btts"
    if (k := k_of(r"(\d+) or more total goals")) is not None or \
       (k := k_of(r"match have (\d+) or more")) is not None:
        return _pct(p_total_goals_geq(k, t)), "total-goals"
    if (k := k_of(r"(\d+) or fewer total goals")) is not None:
        return _pct(1 - p_total_goals_geq(k + 1, t)), "total-goals-under"
    if "tied at halftime" in q or ("halftime" in q and "tied" in q):
        return min(_pct(p_ht_tied(la, lb)), 47 if t >= 2.2 else 99), "ht-tied"
    if "be ahead at halftime" in q or ("at halftime" in q and "be winning" in q):
        side = _team_side(q, ctx)
        if side:
            h = 1 - SECOND_HALF_GOAL_SHARE
            lam_s, lam_o = (la, lb) if side == "a" else (lb, la)
            return _pct(p_more_exact(h * lam_s, h * lam_o)), "ht-lead"
    if "same number of goals" in q and "halves" in q:
        return _pct(_same_goals_both_halves(t)), "halves-same"
    if "goal be scored in each half" in q or "at least one goal" in q and "each half" in q:
        l1, l2 = _half_lams(t)
        return _pct((1 - math.exp(-l1)) * (1 - math.exp(-l2))), "goal-each-half"
    if "second half" in q and ("more goals than the first" in q or
                               "more total goals than the first" in q or
                               "produce more goals" in q):
        return _pct(_second_half_more_goals(t)), "2h-more-goals"
    if (k := k_of(r"second half have (\d+) or more total goals")) is not None:
        return _pct(pois_sf(k, SECOND_HALF_GOAL_SHARE * t)), "2h-goals"
    if (k := k_of(r"first half produce (\d+) or more goals")) is not None:
        return _pct(pois_sf(k, (1 - SECOND_HALF_GOAL_SHARE) * t)), "1h-goals"
    if "score the first goal of the second half" in q:
        side = _team_side(q, ctx)
        if side:
            lam_s = la if side == "a" else lb
            l2 = SECOND_HALF_GOAL_SHARE * t
            return _pct((lam_s / t) * (1 - math.exp(-l2))), "2h-first-goal"
    if "score the first goal" in q:
        side = _team_side(q, ctx)
        if side:
            return _pct(p_scores_first(la if side == "a" else lb, t)), "first-goal"

    # ---- "any player" concentration props (before team-level thresholds) ---
    if re.search(r"any (?:\w+ )?player", q) and \
       (k := k_of(r"(\d+) or more shots on target")) is not None:
        side2 = _team_side(q, ctx)
        lams = [stat[side2]["sot"]] if side2 else [ctx.sot_a, ctx.sot_b]
        # concentration model: top shooter ~30%, next ~22%/15%/15%/18% of team SOT
        shares = (0.30, 0.22, 0.15, 0.15, 0.18)
        p_none = 1.0
        for team_sot in lams:
            for s in shares:
                p_none *= sum(pois_pmf(i, team_sot * s) for i in range(k))
        return _pct(1 - p_none), "any-player-sot"

    # ---- team goal markets --------------------------------------------------
    side = _team_side(q, ctx)
    if side and not re.search(r"any (?:\w+ )?player", q):
        lam_s, lam_o = (la, lb) if side == "a" else (lb, la)
        if "clean sheet" in q:
            return _pct(p_clean_sheet_a(lam_o)), "clean-sheet"
        if "score in the second half" in q:
            return _pct(p_scores_2h(lam_s)), "team-2h"
        if "score in the first half" in q:
            return _pct(p_scores_1h(lam_s)), "team-1h"
        if "score in both halves" in q:
            l1, l2 = _half_lams(lam_s)
            return _pct((1 - math.exp(-l1)) * (1 - math.exp(-l2))), "team-both-halves"
        if re.search(r"score a goal", q):
            return _pct(p_scores(lam_s)), "team-scores"
        if (k := k_of(r"score (?:at least )?(\d+) or more (?:total )?goals?")) is not None or \
           (k := k_of(r"score at least (\d+) goal")) is not None:
            return (_pct(p_scores(lam_s)) if k == 1
                    else _pct(pois_sf(k, lam_s))), "team-goals-k"
        # count-stat thresholds: SOT / corners / cards / offsides / shots
        for word, key in (("shots on target", "sot"), ("corner", "corner"),
                          ("card", "card"), ("offside", "offside"),
                          ("shot", "shot")):
            if word in q:
                lam0 = stat[side][key]
                if "second half" in q:
                    lam0 *= SECOND_HALF_CARD_SHARE if key == "card" else 0.53
                if "first half" in q:
                    lam0 *= 0.45
                k = (k_of(r"(\d+) or more") or k_of(r"at least (\d+)") or
                     k_of(r"offside (\d+) or more times"))
                if k is not None:
                    v = _pct(p_geq(k, lam0))
                    return (_clamp_noisy(v) if key in ("card", "offside") else v), f"team-{key}-k"

    # ---- strict comparisons (tie-trap §5.4) --------------------------------
    for marker, key, half in (("more shots on target than", "sot", None),
                              ("more corner kicks than", "corner", None),
                              ("more cards than", "card", None),
                              ("more fouls than", "foul", None),
                              ("score more goals than", "goal", None)):
        if marker in q:
            sides = _cmp_sides(q, marker, ctx)
            if sides:
                s, o = sides
                ms, mo = stat[s][key], stat[o][key]
                if "second half" in q:
                    share = SECOND_HALF_CARD_SHARE if key == "card" else 0.53
                    ms, mo = ms * share, mo * share
                v = _pct(p_more_exact(ms, mo))
                return (_clamp_noisy(v) if key in ("card", "foul") else v), f"cmp-{key}"

    # ---- match-level count totals ------------------------------------------
    for phrase, lam0, noisy in (
        (r"(\d+) or more total cards", ctx.cards_a + ctx.cards_b, True),
        (r"(\d+) or more total corner", ctx.corners_a + ctx.corners_b, False),
        (r"(\d+) or more total shots on target", ctx.sot_a + ctx.sot_b, False),
        (r"(\d+) or more total shots", ctx.shots_a + ctx.shots_b, False),
        (r"(\d+) or more offside", ctx.offsides_a + ctx.offsides_b, True),
    ):
        if (k := k_of(phrase)) is not None:
            lam = lam0
            if "second half" in q:
                lam *= SECOND_HALF_CARD_SHARE if noisy and "card" in phrase else 0.53
            v = _pct(p_geq(k, lam))
            return (_clamp_noisy(v) if noisy else v), "match-count"
    if "both teams have at least 1 shot on target" in q:
        share = 0.45 if "halftime" in q else (0.55 if "second half" in q else 1.0)
        pa = 1 - math.exp(-share * ctx.sot_a)
        pb = 1 - math.exp(-share * ctx.sot_b)
        return _pct(pa * pb), "both-sot"
    if "both teams receive at least one card" in q:
        pa = 1 - math.exp(-ctx.cards_a)
        pb = 1 - math.exp(-ctx.cards_b)
        return _clamp_noisy(_pct(pa * pb)), "both-carded"
    # ---- drama & exotics (noisy register / D4 fallbacks) --------------------
    if "penalty" in q and "red card" in q:
        return _clamp_noisy(31), "pen-or-red FALLBACK"
    if "penalty kick be awarded" in q:
        return _clamp_noisy(29), "pen FALLBACK"
    if "red card be shown" in q:
        return 15, "red FALLBACK"
    for frag, base in EXOTIC_BASE_RATES.items():
        if frag in q:
            v = base
            return (_clamp_noisy(v) if any(h in frag for h in _NOISY_HINTS) else v), "exotic FALLBACK"
    return None
