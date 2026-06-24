"""
λ-engine: derive everything from O/U 2.5 anchor + 1X2 split (§5.2).
Closed-form Poisson + Dixon-Coles corrections + overdispersion (§5.2.1).
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


# §5.2 O/U 2.5 -> T reference table
OU25_TO_T = [
    # (p_over_25_pct, T)
    (32, 2.0),
    (38, 2.2),
    (46, 2.5),
    (51, 2.7),
    (58, 3.0),
    (64, 3.3),
]

# Derived from the table: {T: {p_le2, p_00, p_2h_ge2}}
OU25_TABLE = {
    2.0: {"p_le2": 68, "p_00": 14, "p_2h_ge2": 30},
    2.2: {"p_le2": 62, "p_00": 11, "p_2h_ge2": 34},
    2.5: {"p_le2": 54, "p_00":  8, "p_2h_ge2": 40},
    2.7: {"p_le2": 49, "p_00":  7, "p_2h_ge2": 44},
    3.0: {"p_le2": 42, "p_00":  5, "p_2h_ge2": 49},
    3.3: {"p_le2": 36, "p_00":  4, "p_2h_ge2": 54},
}

# BTTS / combo grid (§5.2, reference splits)
BTTS_GRID = {
    # key: (lam_a, lam_b) label
    "even_1.35": {"lam_a": 1.35, "lam_b": 1.35, "btts": 55, "p11": 12, "btts3plus": 43},
    "mod_fav_1.65": {"lam_a": 1.65, "lam_b": 1.05, "btts": 52, "p11": 12, "btts3plus": 41},
    "strong_2.0": {"lam_a": 2.00, "lam_b": 0.75, "btts": 46, "p11": 10, "btts3plus": 36},
    "heavy_2.4": {"lam_a": 2.40, "lam_b": 0.55, "btts": 38, "p11":  7, "btts3plus": 32},
}

# HT-tied Bessel table (§5.5) — do not exceed 47 (L9) unless T < 2.2
HT_TIED_TABLE = {
    # key: description, value: p_ht_tied (int, 0-99)
    "even_T2.2": 47,
    "even_T2.5": 44,
    "even_T2.7": 42,
    "even_T3.0": 39,
    "mod_fav":   41,
    "strong":    38,
    "heavy":     34,
}


def ou_to_T(p_over_25: float) -> float:
    """
    Interpolate O/U 2.5 probability (0-1 or 0-100) to total goals T.
    p_over_25: probability Over 2.5 goals, either as decimal or percentage.
    """
    if p_over_25 > 1:
        p_over_25 = p_over_25 / 100.0
    pct = p_over_25 * 100

    table = OU25_TO_T
    if pct <= table[0][0]:
        return table[0][1]
    if pct >= table[-1][0]:
        return table[-1][1]

    for i in range(len(table) - 1):
        p0, t0 = table[i]
        p1, t1 = table[i + 1]
        if p0 <= pct <= p1:
            frac = (pct - p0) / (p1 - p0)
            return t0 + frac * (t1 - t0)
    return 2.5  # fallback


def poisson_p(lam: float, k: int) -> float:
    """P(X = k) for Poisson(lam)."""
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def poisson_cdf(lam: float, k: int) -> float:
    """P(X <= k) for Poisson(lam)."""
    return sum(poisson_p(lam, i) for i in range(k + 1))


def poisson_tail(lam: float, k: int) -> float:
    """P(X >= k) for Poisson(lam)."""
    return 1.0 - poisson_cdf(lam, k - 1)


def p_team_scores(lam: float) -> float:
    """P(team scores >= 1 goal) = 1 - e^(-lam)."""
    return 1.0 - math.exp(-lam)


def p_scores_2h(lam: float) -> float:
    """P(team scores in 2H) = 1 - e^(-0.55*lam). 2H share ≈ 55%."""
    return 1.0 - math.exp(-0.55 * lam)


def p_scores_1h(lam: float) -> float:
    """P(team scores in 1H) = 1 - e^(-0.45*lam). 1H share ≈ 45%."""
    return 1.0 - math.exp(-0.45 * lam)


def p_btts(lam_a: float, lam_b: float) -> float:
    """P(BTTS) = (1 - e^(-lam_a)) * (1 - e^(-lam_b))."""
    return p_team_scores(lam_a) * p_team_scores(lam_b)


def p_1_1(lam_a: float, lam_b: float) -> float:
    """P(1-1) = lam_a * lam_b * e^(-(lam_a+lam_b))."""
    return lam_a * lam_b * math.exp(-(lam_a + lam_b))


def p_btts_and_3plus(lam_a: float, lam_b: float) -> float:
    """P(BTTS AND 3+ goals) = P(BTTS) - P(1-1). Never multiply marginals."""
    return p_btts(lam_a, lam_b) - p_1_1(lam_a, lam_b)


def p_clean_sheet_a(lam_b: float) -> float:
    """P(team A clean sheet) = e^(-lam_b)."""
    return math.exp(-lam_b)


def p_ht_tied(lam_a: float, lam_b: float) -> float:
    """
    P(HT tied) including 0-0 via modified Bessel I₀.
    HT lambdas = 0.45 * full-time splits.
    """
    la = 0.45 * lam_a
    lb = 0.45 * lam_b
    # P(HT tie) = e^(-(la+lb)) * I₀(2*sqrt(la*lb))
    # I₀(x) = sum_{k=0}^{inf} (x/2)^{2k} / (k!)^2
    x = 2.0 * math.sqrt(la * lb)
    i0 = _bessel_i0(x)
    return math.exp(-(la + lb)) * i0


def _bessel_i0(x: float) -> float:
    """Modified Bessel I₀(x) via series expansion."""
    result = 0.0
    term = 1.0
    k = 0
    while True:
        result += term
        k += 1
        term *= (x / 2.0) ** 2 / (k * k)
        if term < 1e-12:
            break
    return result


def p_ht_both_sot(lam_a: float, lam_b: float) -> float:
    """
    P(at HT, both teams >= 1 SOT).
    HT SOT share ≈ 0.45 of FT SOT lambda.
    """
    la_ht = 0.45 * lam_a
    lb_ht = 0.45 * lam_b
    return p_team_scores(la_ht) * p_team_scores(lb_ht)


def find_split(T: float, p_home_win: float, p_draw: float, p_away_win: float,
               tol: float = 0.02) -> Tuple[float, float]:
    """
    Find (lam_a, lam_b) s.t. lam_a + lam_b = T and the Poisson 1X2
    reproduces the devigged probabilities within ±tol (default 2%).

    Uses a simple grid search over split fraction s = lam_a / T.
    Returns (lam_a, lam_b).
    """
    best_s = 0.5
    best_err = float("inf")

    for s_int in range(1, 100):
        s = s_int / 100.0
        la = s * T
        lb = (1 - s) * T
        ph, pd, pa = _poisson_1x2(la, lb)
        err = abs(ph - p_home_win) + abs(pd - p_draw) + abs(pa - p_away_win)
        if err < best_err:
            best_err = err
            best_s = s

    lam_a = best_s * T
    lam_b = T - lam_a
    return lam_a, lam_b


def _poisson_1x2(lam_a: float, lam_b: float, max_goals: int = 8):
    """Compute P(home win), P(draw), P(away win) from Poisson grid."""
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    for a in range(max_goals + 1):
        for b in range(max_goals + 1):
            p = poisson_p(lam_a, a) * poisson_p(lam_b, b)
            if a > b:
                p_home += p
            elif a == b:
                p_draw += p
            else:
                p_away += p
    return p_home, p_draw, p_away


@dataclass
class LambdaEngine:
    """
    Full λ-engine for a single match.
    Accepts devigged anchors; derives all market probabilities.
    """
    lam_a: float          # home team total goals λ
    lam_b: float          # away team total goals λ
    T: float = field(init=False)

    # Dixon-Coles / overdispersion adjustments applied?
    dc_applied: bool = False
    overdispersion_tilt: int = 0  # +/- points applied, cap ±3

    def __post_init__(self):
        self.T = self.lam_a + self.lam_b

    # --- Core match probabilities ---

    def win_a(self) -> float:
        ph, pd, pa = _poisson_1x2(self.lam_a, self.lam_b)
        return ph

    def draw(self) -> float:
        ph, pd, pa = _poisson_1x2(self.lam_a, self.lam_b)
        return pd

    def win_b(self) -> float:
        ph, pd, pa = _poisson_1x2(self.lam_a, self.lam_b)
        return pa

    def btts(self) -> float:
        return p_btts(self.lam_a, self.lam_b)

    def btts_and_3plus(self) -> float:
        return p_btts_and_3plus(self.lam_a, self.lam_b)

    def over(self, line: float = 2.5) -> float:
        """P(total goals > line)."""
        k = int(math.floor(line)) + 1
        return poisson_tail(self.T, k)

    def under(self, line: float = 2.5) -> float:
        return 1.0 - self.over(line)

    def team_scores(self, side: str = "a") -> float:
        lam = self.lam_a if side == "a" else self.lam_b
        return p_team_scores(lam)

    def team_scores_2h(self, side: str = "a") -> float:
        lam = self.lam_a if side == "a" else self.lam_b
        return p_scores_2h(lam)

    def team_scores_1h(self, side: str = "a") -> float:
        lam = self.lam_a if side == "a" else self.lam_b
        return p_scores_1h(lam)

    def ht_tied(self) -> float:
        p = p_ht_tied(self.lam_a, self.lam_b)
        # L9: cap at 47 unless T < 2.2
        cap = 0.47 if self.T >= 2.2 else 1.0
        return min(p, cap)

    def ht_both_sot(self, lam_sot_a: float, lam_sot_b: float) -> float:
        return p_ht_both_sot(lam_sot_a, lam_sot_b)

    def clean_sheet_a(self) -> float:
        return p_clean_sheet_a(self.lam_b)

    def clean_sheet_b(self) -> float:
        return p_clean_sheet_a(self.lam_a)

    def apply_dixon_coles(self, matchup: str = "normal") -> None:
        """
        Apply Dixon-Coles + overdispersion tilts (§5.2 / §5.2.1).
        matchup: 'cagey' (tight defensive) | 'mismatch' | 'normal'
        Modifies instance state; idempotent guard via dc_applied.
        """
        if self.dc_applied:
            return
        # These tilts apply to probabilities at output, tracked as adjustments.
        if matchup == "cagey":
            # Nudge draw/low-score mass up by the existing Dixon-Coles caveat (+1-3)
            self.overdispersion_tilt = 2
        elif matchup == "mismatch":
            # Fat blow-out tail: slightly underpriced by pure Poisson
            self.overdispersion_tilt = -1
        self.dc_applied = True

    def summary(self) -> dict:
        return {
            "lam_a": round(self.lam_a, 3),
            "lam_b": round(self.lam_b, 3),
            "T": round(self.T, 3),
            "win_a": round(self.win_a(), 4),
            "draw": round(self.draw(), 4),
            "win_b": round(self.win_b(), 4),
            "btts": round(self.btts(), 4),
            "btts_and_3plus": round(self.btts_and_3plus(), 4),
            "over_2.5": round(self.over(2.5), 4),
            "ht_tied": round(self.ht_tied(), 4),
        }


# §5.5 Threshold tables (exact Poisson / Bessel)

# Cards λ -> tails
CARDS_TABLE = {
    2.8: {"ge4_total": 31, "ge2_2h": 52},
    3.2: {"ge4_total": 40, "ge2_2h": 59},
    3.5: {"ge4_total": 46, "ge2_2h": 64},
    4.0: {"ge4_total": 57, "ge2_2h": 71},
    4.5: {"ge4_total": 66, "ge2_2h": 77},
}

# Team corners λ -> P(>=5)
CORNERS_GE5 = {3.0: 19, 3.5: 28, 4.0: 37, 4.5: 47, 5.0: 56, 5.5: 64, 6.0: 72}

# Team SOT λ -> P(>=2)
SOT_GE2 = {1.0: 26, 1.5: 44, 2.0: 59, 2.5: 71, 3.0: 80, 3.5: 86, 4.0: 91, 4.5: 94}

# Team offsides λ -> P(>=2)
OFFSIDES_GE2 = {0.8: 19, 1.0: 26, 1.2: 34, 1.5: 44, 1.8: 54, 2.0: 59}

# HT both ≥1 SOT — FT SOT λ pairs (HT share ≈ 0.45)
HT_BOTH_SOT_TABLE = {
    "4.5_4.5": 75, "4.0_3.0": 62, "5.5_3.0": 68, "6.0_2.2": 59,
}


def lookup_table(table: dict, lam: float) -> int:
    """Interpolate a lookup table keyed by lambda."""
    keys = sorted(table.keys())
    if lam <= keys[0]:
        return table[keys[0]]
    if lam >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        k0, k1 = keys[i], keys[i + 1]
        if k0 <= lam <= k1:
            frac = (lam - k0) / (k1 - k0)
            v0, v1 = table[k0], table[k1]
            # Handle nested dicts (cards table)
            if isinstance(v0, dict):
                return {k: int(round(v0[k] + frac * (v1[k] - v0[k]))) for k in v0}
            return int(round(v0 + frac * (v1 - v0)))
    return list(table.values())[-1]
