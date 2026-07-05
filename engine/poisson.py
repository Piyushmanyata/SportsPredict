"""§5.2 / §5.2.1 / §5.7 — the λ engine.

Fit total goals T from the devigged O/U 2.5 price, split into team rates
(λ_A + λ_B = T) so the Poisson score grid reproduces the devigged 1X2 within
±2 pts, then read every derived market off closed forms / the score grid.

Dixon–Coles + overdispersion tilts are exposed as an explicit, capped (±3 pts)
helper so they are logged, never silently baked in (D2/L14: do not double-count).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .constants import SHARE_1H, SHARE_2H

GRID_MAX = 12  # goals per team in the score grid (covers T up to ~5 comfortably)


def pois_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def pois_cdf(k: int, lam: float) -> float:
    return sum(pois_pmf(i, lam) for i in range(k + 1))


def p_over(total_line_goals: int, T: float) -> float:
    """P(total goals >= total_line_goals) for match total ~ Poisson(T)."""
    return 1.0 - pois_cdf(total_line_goals - 1, T)


def fit_T_from_over25(p_over25: float) -> float:
    """Invert P(N ≥ 3 | N~Poisson(T)) = p_over25 by bisection."""
    lo, hi = 0.3, 8.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if p_over(3, mid) < p_over25:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def score_grid_1x2(lam_a: float, lam_b: float) -> tuple[float, float, float]:
    """(home win, draw, away win) off the independent-Poisson score grid."""
    pa = [pois_pmf(i, lam_a) for i in range(GRID_MAX + 1)]
    pb = [pois_pmf(i, lam_b) for i in range(GRID_MAX + 1)]
    win = draw = loss = 0.0
    for i in range(GRID_MAX + 1):
        for j in range(GRID_MAX + 1):
            p = pa[i] * pb[j]
            if i > j:
                win += p
            elif i == j:
                draw += p
            else:
                loss += p
    return win, draw, loss


def fit_split_to_1x2(T: float, p_home: float, p_away: float) -> tuple[float, float]:
    """Find λ_A (with λ_B = T − λ_A) whose grid 1X2 best matches the devigged
    line. Coarse grid then golden-ish refinement; target ±2 pts (§5.2)."""
    def err(la: float) -> float:
        w, _, l = score_grid_1x2(la, T - la)
        return (w - p_home) ** 2 + (l - p_away) ** 2

    lo, hi = 0.05, T - 0.05
    best_la, best_e = lo, err(lo)
    steps = 60
    for i in range(1, steps + 1):
        la = lo + (hi - lo) * i / steps
        e = err(la)
        if e < best_e:
            best_la, best_e = la, e
    # local refine
    span = (hi - lo) / steps
    for _ in range(30):
        for cand in (best_la - span / 2, best_la + span / 2):
            if lo <= cand <= hi and err(cand) < best_e:
                best_la, best_e = cand, err(cand)
        span *= 0.6
    return best_la, T - best_la


def dixon_coles_tilt(matchup: str = "neutral") -> dict[str, float]:
    """§5.2/§5.2.1 — suggested capped tilts in probability points.
    ONE combined Dixon–Coles + overdispersion adjustment (never double-count),
    total cap ±3. Log as `overdispersion-tilt` when applied.

    matchup: 'cagey' (tight/defensive), 'neutral', 'mismatch' (heavy favourite).
    Returns pts to ADD to each named outcome class.
    """
    if matchup == "cagey":
        return {"draw": +2, "under": +2, "btts": -2, "clean_sheet": +2,
                "zero_zero": +1, "ht_tied": +1}
    if matchup == "mismatch":
        # fat 4+ tail: overs / heavy-favourite scores-2+ mildly underpriced
        return {"over_3plus": +1, "fav_scores_2plus": +1}
    return {"draw": +1, "btts": -1}


@dataclass
class MatchModel:
    """One match's fitted λ model and every §5 closed form off it.

    Build with `MatchModel.from_anchors(...)` (preferred) or direct λs.
    All outputs are probabilities in [0,1].
    """
    name: str
    lam_a: float
    lam_b: float
    meta: dict = field(default_factory=dict)

    @property
    def T(self) -> float:
        return self.lam_a + self.lam_b

    @classmethod
    def from_anchors(cls, name: str, p_over25: float, p_home: float,
                     p_draw: float, p_away: float) -> "MatchModel":
        """Fit from devigged O/U 2.5 and 1X2. Stores fit quality in meta —
        check meta['fit_1x2_max_err'] ≤ 0.02 per §5.2."""
        T = fit_T_from_over25(p_over25)
        la, lb = fit_split_to_1x2(T, p_home, p_away)
        m = cls(name, la, lb)
        w, d, l = score_grid_1x2(la, lb)
        m.meta = {
            "T": T,
            "grid_1x2": (w, d, l),
            "anchor_1x2": (p_home, p_draw, p_away),
            "fit_1x2_max_err": max(abs(w - p_home), abs(l - p_away)),
        }
        return m

    # ── archetype #1: win (grid; apply L12 draw discipline upstream via anchors)
    def p_1x2(self) -> tuple[float, float, float]:
        return score_grid_1x2(self.lam_a, self.lam_b)

    # ── archetype #2: totals
    def p_total_at_least(self, k: int) -> float:
        return p_over(k, self.T)

    def p_total_at_most(self, k: int) -> float:
        return pois_cdf(k, self.T)

    def p_zero_zero(self) -> float:
        return math.exp(-self.T)

    # ── archetype #5 / #4: team scores (FT / halves)
    def p_scores(self, team: str) -> float:
        lam = self.lam_a if team == "a" else self.lam_b
        return 1.0 - math.exp(-lam)

    def p_scores_2h(self, team: str) -> float:
        lam = self.lam_a if team == "a" else self.lam_b
        return 1.0 - math.exp(-SHARE_2H * lam)

    def p_scores_1h(self, team: str) -> float:
        lam = self.lam_a if team == "a" else self.lam_b
        return 1.0 - math.exp(-SHARE_1H * lam)

    # ── archetype #3 and friends
    def p_btts(self) -> float:
        return (1 - math.exp(-self.lam_a)) * (1 - math.exp(-self.lam_b))

    def p_1_1(self) -> float:
        return self.lam_a * self.lam_b * math.exp(-self.T)

    def p_btts_and_3plus(self) -> float:
        """BTTS ∧ 3+ = BTTS − P(1-1). Never multiply marginals (correlated).
        L6: read this off the anchor-implied T, never freestyle below it."""
        return self.p_btts() - self.p_1_1()

    def p_clean_sheet(self, team: str) -> float:
        lam_opp = self.lam_b if team == "a" else self.lam_a
        return math.exp(-lam_opp)

    # ── archetype #7 (goals flavour): 2+ total goals in 2H
    def p_2h_goals_at_least(self, k: int) -> float:
        lam_2h = SHARE_2H * self.T
        return 1.0 - pois_cdf(k - 1, lam_2h)

    # ── archetype #11: joint/sequence (§5.7)
    def p_scores_first(self, team: str) -> float:
        lam = self.lam_a if team == "a" else self.lam_b
        return (lam / self.T) * (1.0 - math.exp(-self.T))


def p_scores_first_and_other_scores_2h(model: MatchModel, first_team: str,
                                       second_team: str,
                                       haircut: float = 0.015) -> float:
    """§5.7 — 'A scores first AND B scores in 2H': product minus a small
    dependence haircut (default −1.5 pts). Never above either marginal.
    Joint props inherit ALL λ-estimation risk of both marginals (L8)."""
    p_first = model.p_scores_first(first_team)
    p_2h = model.p_scores_2h(second_team)
    p = p_first * p_2h - haircut
    return max(0.01, min(p, p_first, p_2h))
