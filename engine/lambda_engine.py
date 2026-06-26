"""
λ Engine (§5.2) — derive all probabilities from two anchored numbers:
  1. O/U 2.5 price → total goals T
  2. Devigged 1X2 → λ_A, λ_B split that reproduces the 1X2 within ±2 pts

All probabilities returned as floats in [0, 1] (not integers).
"""

import math
from dataclasses import dataclass, field
from scipy.optimize import root_scalar, minimize_scalar


# ---------------------------------------------------------------------------
# O/U 2.5 → T lookup table (§5.2 — exact values from the spec)
# ---------------------------------------------------------------------------
_OU25_TABLE = [
    # (P(Over 2.5), T)
    (0.32, 2.0),
    (0.38, 2.2),
    (0.46, 2.5),
    (0.51, 2.7),
    (0.58, 3.0),
    (0.64, 3.3),
]


def ou25_to_T(p_over: float) -> float:
    """
    Convert devigged P(Over 2.5) to expected total goals T via Poisson inversion.
    Interpolates between the spec table anchor points.
    p_over: float in [0,1].
    """
    # Exact inversion: P(Over 2.5) = 1 - P(0) - P(1) - P(2) under Poisson(T)
    # = 1 - e^-T(1 + T + T²/2)
    def p_over_poisson(T):
        return 1 - math.exp(-T) * (1 + T + T ** 2 / 2)

    # Solve for T in [0.5, 8]
    try:
        sol = root_scalar(
            lambda T: p_over_poisson(T) - p_over,
            bracket=[0.5, 8.0],
            method="brentq",
        )
        return sol.root
    except Exception:
        # Fallback: linear interpolation on spec table
        xs = [r[0] for r in _OU25_TABLE]
        ys = [r[1] for r in _OU25_TABLE]
        if p_over <= xs[0]:
            return ys[0]
        if p_over >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= p_over <= xs[i + 1]:
                t = (p_over - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return 2.5


def poisson_cdf(lam: float, k: int) -> float:
    """P(X <= k) for X ~ Poisson(lam)."""
    cumulative = 0.0
    term = math.exp(-lam)
    cumulative += term
    for i in range(1, k + 1):
        term *= lam / i
        cumulative += term
    return cumulative


def poisson_pmf(lam: float, k: int) -> float:
    """P(X = k) for X ~ Poisson(lam)."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def poisson_table(lam: float) -> dict:
    """Pre-compute common Poisson tail probabilities for a single λ."""
    p0 = math.exp(-lam)
    return {
        "p_at_least_1": 1 - p0,
        "p_0": p0,
        "p_1": poisson_pmf(lam, 1),
        "p_2": poisson_pmf(lam, 2),
        "p_3plus": 1 - poisson_cdf(lam, 2),
        "p_at_least_2": 1 - poisson_cdf(lam, 1),
        "p_at_least_5": 1 - poisson_cdf(lam, 4),
    }


def _1x2_from_split(lam_a: float, lam_b: float, max_goals: int = 10) -> tuple[float, float, float]:
    """
    Compute P(home win), P(draw), P(away win) from Poisson(lam_a) × Poisson(lam_b).
    """
    p_home = p_draw = p_away = 0.0
    for a in range(max_goals + 1):
        pa = poisson_pmf(lam_a, a)
        for b in range(max_goals + 1):
            pb = poisson_pmf(lam_b, b)
            if a > b:
                p_home += pa * pb
            elif a == b:
                p_draw += pa * pb
            else:
                p_away += pa * pb
    return p_home, p_draw, p_away


def fit_lambda_split(
    T: float,
    p_home_target: float,
    p_draw_target: float | None = None,
) -> tuple[float, float]:
    """
    Find (lam_a, lam_b) with lam_a + lam_b = T such that the Poisson 1X2 grid
    reproduces p_home_target within ±2 pts. If p_draw_target is also supplied,
    tries to match both (home and draw) simultaneously.

    Returns (lam_a, lam_b).
    """
    def objective(lam_a):
        lam_b = T - lam_a
        if lam_b <= 0:
            return 1e9
        ph, pd, pa = _1x2_from_split(lam_a, lam_b)
        return (ph - p_home_target) ** 2

    result = minimize_scalar(objective, bounds=(0.01, T - 0.01), method="bounded")
    lam_a = result.x
    lam_b = T - lam_a
    return lam_a, lam_b


@dataclass
class LambdaModel:
    """
    Container for a fully resolved match λ model.

    Attributes
    ----------
    lam_a, lam_b : float
        Expected goals per team (full match).
    T : float
        Total goals = lam_a + lam_b.
    sigma_a, sigma_b : float
        λ uncertainty for L8 MC (§5.11). Default: 0.15 × lam.
    """
    lam_a: float
    lam_b: float
    sigma_a: float = field(init=False)
    sigma_b: float = field(init=False)
    _sigma_a_override: float | None = field(default=None, repr=False)
    _sigma_b_override: float | None = field(default=None, repr=False)

    def __post_init__(self):
        self.sigma_a = self._sigma_a_override if self._sigma_a_override is not None else 0.15 * self.lam_a
        self.sigma_b = self._sigma_b_override if self._sigma_b_override is not None else 0.15 * self.lam_b

    @property
    def T(self) -> float:
        return self.lam_a + self.lam_b

    @classmethod
    def from_ou25_and_1x2(
        cls,
        p_over_25: float,
        p_home: float,
        p_draw: float | None = None,
        sigma_a: float | None = None,
        sigma_b: float | None = None,
    ) -> "LambdaModel":
        """Build a LambdaModel from devigged O/U 2.5 and 1X2 prices."""
        T = ou25_to_T(p_over_25)
        lam_a, lam_b = fit_lambda_split(T, p_home, p_draw)
        return cls(lam_a=lam_a, lam_b=lam_b, _sigma_a_override=sigma_a, _sigma_b_override=sigma_b)

    # ------------------------------------------------------------------
    # Closed-form market probabilities (§5.2)
    # ------------------------------------------------------------------
    def p_team_scores(self, team: str = "a") -> float:
        """P(team scores ≥ 1 in 90 min) = 1 − e^(−λ)."""
        lam = self.lam_a if team == "a" else self.lam_b
        return 1 - math.exp(-lam)

    def p_team_scores_2h(self, team: str = "a") -> float:
        """P(team scores in 2H) = 1 − e^(−0.55·λ)."""
        lam = self.lam_a if team == "a" else self.lam_b
        return 1 - math.exp(-0.55 * lam)

    def p_team_scores_1h(self, team: str = "a") -> float:
        """P(team scores in 1H) = 1 − e^(−0.45·λ)."""
        lam = self.lam_a if team == "a" else self.lam_b
        return 1 - math.exp(-0.45 * lam)

    def p_btts(self) -> float:
        """P(both teams score) = (1−e^−λA)(1−e^−λB)."""
        return (1 - math.exp(-self.lam_a)) * (1 - math.exp(-self.lam_b))

    def p_11(self) -> float:
        """P(1-1 draw) = λA·λB·e^(−T)."""
        return self.lam_a * self.lam_b * math.exp(-self.T)

    def p_btts_and_3plus(self) -> float:
        """P(BTTS ∧ 3+ goals) = P(BTTS) − P(1-1) — never multiply marginals."""
        return self.p_btts() - self.p_11()

    def p_clean_sheet_a(self) -> float:
        """P(team B scores 0) = e^(−λB)."""
        return math.exp(-self.lam_b)

    def p_clean_sheet_b(self) -> float:
        """P(team A scores 0) = e^(−λA)."""
        return math.exp(-self.lam_a)

    def p_over_goals(self, line: float = 2.5) -> float:
        """P(total goals > line) under Poisson(T)."""
        k = int(math.floor(line))
        return 1 - poisson_cdf(self.T, k)

    def p_2h_goals_gte(self, n: int = 2) -> float:
        """P(total 2H goals ≥ n), 2H share ≈ 55%."""
        lam_2h = 0.55 * self.T
        return 1 - poisson_cdf(lam_2h, n - 1)

    def p_1x2(self) -> tuple[float, float, float]:
        """Return (p_home, p_draw, p_away) from the Poisson grid."""
        return _1x2_from_split(self.lam_a, self.lam_b)

    def p_win_a(self) -> float:
        return self.p_1x2()[0]

    def p_draw(self) -> float:
        return self.p_1x2()[1]

    def p_win_b(self) -> float:
        return self.p_1x2()[2]

    def p_score_first(self, team: str = "a") -> float:
        """P(team scores first) ≈ (λ / T) × (1 − e^−T)."""
        lam = self.lam_a if team == "a" else self.lam_b
        if self.T < 0.01:
            return 0.5
        return (lam / self.T) * (1 - math.exp(-self.T))
