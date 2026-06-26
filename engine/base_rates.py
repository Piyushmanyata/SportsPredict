"""
Empirical Bayes base-rate tracker (§5.8).

Working values from the spec updated here after each settle audit.
Posterior = (observed + k × prior) / (n_matches + k)
k = 7 for n < 30 observations, then 15.

These values are updated IN PLACE in this file after each deep audit.
"""

from dataclasses import dataclass, field


@dataclass
class BaseRateTracker:
    """
    Tracks tournament-specific event rates via Empirical Bayes.

    Attributes correspond to §5.8 quantities.
    Working values reflect @118 settled state (v8).
    """

    # ---- Priors (VAR-era majors) ----
    prior_pen_per_match:    float = 0.36   # P(pen) ≈ 26-34
    prior_red_per_match:    float = 0.06   # P(red) ≈ 5-8
    prior_pen_or_red:       float = 0.34   # union, small overlap
    prior_cards_mean:       float = 3.5    # 3.2-4.2 (ref ±1)
    prior_goals_per_match:  float = 2.55   # group stage 2.4-2.7

    # ---- Tournament-to-date counts (update after each settle audit) ----
    n_matches:              int   = 0
    obs_pens:               float = 0.0
    obs_reds:               float = 0.0
    obs_pen_or_red:         float = 0.0
    obs_cards_total:        float = 0.0
    obs_goals_total:        float = 0.0

    # ---- v8 working values (§5.8) ----
    # These are the values the engine uses; recomputed by update() or set manually.
    _pen_working:     float = field(default=0.29, repr=True)
    _red_working:     float = field(default=0.06, repr=True)
    _por_working:     float = field(default=0.31, repr=True)
    _cards_working:   float = field(default=3.5,  repr=True)
    _goals_working:   float = field(default=2.55, repr=True)

    @property
    def k(self) -> int:
        """§5.8 stepwise k: 7 for n < 30, else 15."""
        return 7 if self.n_matches < 30 else 15

    def update(
        self,
        pens: float = 0.0,
        reds: float = 0.0,
        pen_or_red: float = 0.0,
        cards: float = 0.0,
        goals: float = 0.0,
        n_new_matches: int = 1,
    ) -> None:
        """
        Ingest results from newly settled matches and recompute posteriors.
        All arguments are totals for the new batch (not per-match rates).
        """
        self.n_matches    += n_new_matches
        self.obs_pens     += pens
        self.obs_reds     += reds
        self.obs_pen_or_red += pen_or_red
        self.obs_cards_total += cards
        self.obs_goals_total += goals
        self._recompute()

    def _recompute(self) -> None:
        k = self.k
        n = self.n_matches
        if n == 0:
            return
        self._pen_working   = (self.obs_pens        + k * self.prior_pen_per_match)   / (n + k)
        self._red_working   = (self.obs_reds         + k * self.prior_red_per_match)   / (n + k)
        self._por_working   = (self.obs_pen_or_red   + k * self.prior_pen_or_red)      / (n + k)
        self._cards_working = (self.obs_cards_total  + k * self.prior_cards_mean * n)  / (n * (1 + k / n))
        self._goals_working = (self.obs_goals_total  + k * self.prior_goals_per_match * n) / (n * (1 + k / n))

    # ---- Accessors ----
    @property
    def pen_rate(self) -> float:
        return self._pen_working

    @property
    def red_rate(self) -> float:
        return self._red_working

    @property
    def pen_or_red_rate(self) -> float:
        return self._por_working

    @property
    def cards_mean(self) -> float:
        return self._cards_working

    @property
    def goals_mean(self) -> float:
        return self._goals_working

    def summary(self) -> dict:
        return {
            "n_matches":     self.n_matches,
            "pen_rate":      round(self._pen_working, 3),
            "red_rate":      round(self._red_working, 3),
            "pen_or_red":    round(self._por_working, 3),
            "cards_mean":    round(self._cards_working, 2),
            "goals_mean":    round(self._goals_working, 2),
        }


# ---------------------------------------------------------------------------
# Module-level singleton — working values from @118 audit (v8, §5.8)
# ---------------------------------------------------------------------------
TRACKER = BaseRateTracker(
    n_matches       = 30,     # approximate matches settled @118 markets
    obs_pens        = 1.0,    # 1 YES (MEX-RSA) in ~5 observed
    obs_reds        = 0.0,
    obs_pen_or_red  = 1.0,
    obs_cards_total = 105.0,  # ≈ 3.5 × 30
    obs_goals_total = 76.5,   # ≈ 2.55 × 30
    _pen_working    = 0.29,
    _red_working    = 0.06,
    _por_working    = 0.31,
    _cards_working  = 3.5,
    _goals_working  = 2.55,
)
