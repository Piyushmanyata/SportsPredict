"""
Feedback loop v3 — §9 of the system instructions.
Outcome decoding · Brier benchmarks · worst-Brier autopsy ·
probability-band decomposition · RBP computation.
"""

from __future__ import annotations
import math


# ─── §9.2  Outcome decoding (no search needed) ────────────────────────────────

def decode_outcome(p_submitted: int, brier_score: float,
                   eps: float = 0.005) -> int | None:
    """
    Decode market outcome from submitted probability integer (1–99) and Brier score.
    Returns 1 (YES), 0 (NO), or None (ambiguous — p exactly 50 per D3).

    Algorithm (§9.2):
      o = 1  iff  (p/100 − 1)² ≈ brier_score
      o = 0  iff  (p/100 − 0)² ≈ brier_score
    Equivalently: miss = 100·√brier; if miss ≈ 100−p then o=1, else o=0.
    """
    p = p_submitted / 100.0
    brier_if_yes = (p - 1.0) ** 2
    brier_if_no  = p ** 2

    if abs(brier_if_yes - brier_score) < eps:
        return 1
    if abs(brier_if_no - brier_score) < eps:
        return 0
    return None  # ambiguous (usually p near 50)


def decode_all(results: list[dict], eps: float = 0.005) -> list[dict]:
    """
    Decode outcomes for a list of settled result dicts.
    Each dict must have 'probability_submitted' (0–1 decimal) and 'brier_score'.
    Appends 'outcome' (1/0/None) and 'p_int' (integer) to each.
    """
    out = []
    for r in results:
        p_dec = r.get('probability_submitted') or r.get('probability', 0.5)
        p_int = round(p_dec * 100)
        brier = r.get('brier_score', 0.0)
        outcome = decode_outcome(p_int, brier, eps)
        out.append({**r, 'p_int': p_int, 'outcome': outcome})
    return out


# ─── §9.1  Brier benchmarks ───────────────────────────────────────────────────

def self_expected_brier(predictions: list[dict]) -> float:
    """
    Self-expected Brier = Σ p·(1−p) / n.
    predictions: list of dicts with 'probability' (0–1 decimal from API).
    """
    if not predictions:
        return 0.0
    return sum(
        p['probability'] * (1 - p['probability'])
        for p in predictions
    ) / len(predictions)


def realized_mean_brier(results: list[dict]) -> float:
    """Realized mean Brier from settled results with 'brier_score' field."""
    settled = [r for r in results if r.get('brier_score') is not None]
    if not settled:
        return 0.0
    return sum(r['brier_score'] for r in settled) / len(settled)


def noise_band_sigma(n: int, sd: float = 0.15) -> float:
    """
    σ of the mean Brier = sd / √n.
    Use sd=0.15 as central estimate; range 0.12–0.18 per §9.1.
    """
    if n <= 0:
        return float('inf')
    return sd / math.sqrt(n)


def calibration_verdict(gap: float, n: int) -> str:
    """
    GREEN / AMBER / RED from gap and sample size.
    React only beyond ~1.5 noise bands (§9.1).
    """
    band = noise_band_sigma(n)
    if band == 0:
        return "N/A"
    sigma = gap / band
    if sigma < 1.5:
        return "GREEN"
    if sigma < 2.5:
        return "AMBER"
    return "RED"


# ─── §9.3  Worst-Brier autopsy ────────────────────────────────────────────────

AUTOPSY_TAXONOMY = (
    "bad anchor",
    "missed news/lineup",
    "wording misread",
    "tie-trap miss",
    "λ/T misread",
    "correlated-axis hit (L8)",
    "pure noise (no fix)",
)


def top_worst_brier(results: list[dict], n: int = 3) -> list[dict]:
    """Return the n worst Brier markets from settled results."""
    settled = [r for r in results if r.get('brier_score') is not None]
    return sorted(settled, key=lambda r: r['brier_score'], reverse=True)[:n]


def autopsy_market(market: dict) -> str:
    """
    One-line autopsy suggestion for a high-Brier market.
    Caller should verify and override — this is a prompt, not a verdict.
    """
    b = market.get('brier_score', 0)
    outcome = market.get('outcome')
    p = market.get('p_int', 50) / 100.0
    archetype = market.get('archetype', 'unknown')

    if archetype in ('drama', 'strict_compare') and b > 0.4:
        if archetype == 'drama':
            return "pure noise (no fix) — drama market, stay near base rates (L5)"
        return "correlated-axis hit or game-state misread — verify λ and game script"

    if archetype == 'win' and b > 0.3:
        return "λ/T misread or L12 upset/draw — check DC draw inflation was applied"

    if archetype == 'player_prop' and b > 0.3:
        if outcome == 1 and p < 0.50:
            return "L10: band ran hot — check driver gate was applied and rotation risk"
        return "missed news/lineup — rotation or minutes adjustment needed"

    if archetype == 'strict_compare' and b > 0.35:
        return "tie-trap miss — verify §5.4 table was used, not raw 50"

    if b > 0.5:
        return "correlated-axis hit (L8) — check if >4 markets on same latent axis"

    return "pure noise (no fix) — within expected variance for this archetype"


# ─── §9.5  Probability-band decomposition ────────────────────────────────────

# Bands matching the ~10pt spec; 50–55 and 55–70 are split per the audit
_BANDS = [
    (0.00, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40),
    (0.40, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.70),
    (0.70, 0.80), (0.80, 0.90), (0.90, 1.00),
]


def band_decomposition(predictions_with_outcomes: list[dict]) -> list[dict]:
    """
    Fine-grained probability-band decomposition (§9.5 item 2).

    Input: list of dicts with:
      'probability' (0–1 float), 'outcome' (1/0), 'brier_score' (float).

    Returns list of band summaries: band, n, avg_predicted_pct,
    hit_rate_pct, gap_pp, sigma.
    """
    results = []
    for lo, hi in _BANDS:
        bucket = [
            r for r in predictions_with_outcomes
            if lo <= r.get('probability', -1) < hi
            and r.get('outcome') is not None
        ]
        if not bucket:
            continue
        n = len(bucket)
        avg_p = sum(r['probability'] for r in bucket) / n
        hit_rate = sum(r['outcome'] for r in bucket) / n
        gap = hit_rate - avg_p
        # Binomial SD approximation
        binom_sd = math.sqrt(avg_p * (1 - avg_p) / n) if n > 0 else 1.0
        sigma = gap / binom_sd if binom_sd > 0 else 0.0
        results.append({
            'band':              f"{int(lo*100)}–{int(hi*100)}%",
            'n':                 n,
            'avg_predicted_pct': round(avg_p * 100, 1),
            'hit_rate_pct':      round(hit_rate * 100, 1),
            'gap_pp':            round(gap * 100, 1),
            'sigma':             round(sigma, 2),
            'flag':              '⚑' if abs(sigma) >= 0.8 else '',
        })
    return results


def group_by_match(decoded_results: list[dict]) -> dict[str, list[dict]]:
    """Group decoded results by match name or match_id."""
    groups: dict[str, list[dict]] = {}
    for r in decoded_results:
        key = r.get('match_name') or r.get('match_id', 'unknown')
        groups.setdefault(key, []).append(r)
    return groups


def per_match_brier(decoded_results: list[dict]) -> list[dict]:
    """
    §9.5 item 1: per-match Brier table.
    Dominant variance axis — match-level λ quality beats archetype tuning.
    """
    groups = group_by_match(decoded_results)
    table = []
    for match, mkts in groups.items():
        n = len(mkts)
        avg_b = sum(m['brier_score'] for m in mkts) / n if n else 0.0
        table.append({'match': match, 'n': n, 'avg_brier': round(avg_b, 3)})
    return sorted(table, key=lambda r: r['avg_brier'])


# ─── §9.6  RBP computation ───────────────────────────────────────────────────

def compute_rbp(your_brier: float, crowd_brier: float,
                stage_weight: float = 1.0) -> float:
    """
    RBP per market = (crowd_brier − your_brier) × 100 × stage_weight.
    Positive = you beat the crowd.
    """
    return (crowd_brier - your_brier) * 100.0 * stage_weight


def aggregate_rbp(markets: list[dict]) -> dict:
    """
    Aggregate RBP summary.
    Each market dict needs: 'your_brier', 'crowd_brier', optionally 'stage_weight'.
    """
    scored = [m for m in markets if 'crowd_brier' in m and m['crowd_brier'] is not None]
    if not scored:
        return {'available': False, 'note': 'crowd_brier unavailable — run raw §9.5 audit'}

    total_rbp = sum(
        compute_rbp(m['your_brier'], m['crowd_brier'], m.get('stage_weight', 1.0))
        for m in scored
    )
    n = len(scored)
    beat = sum(1 for m in scored if m['your_brier'] < m['crowd_brier'])

    return {
        'available':          True,
        'n_markets':          n,
        'total_weighted_rbp': round(total_rbp, 2),
        'avg_rbp_per_market': round(total_rbp / n, 3) if n else 0,
        'beat_crowd_count':   beat,
        'beat_crowd_pct':     round(beat / n * 100, 1) if n else 0,
    }


def match_rbp_table(decoded_results: list[dict]) -> list[dict]:
    """
    §9.6: per-match RBP table — primary contest ranking.
    Requires 'crowd_brier' on each result.
    """
    groups = group_by_match(decoded_results)
    table = []
    for match, mkts in groups.items():
        stage_w = mkts[0].get('stage_weight', 1.0) if mkts else 1.0
        your_avg = sum(m['brier_score'] for m in mkts) / len(mkts) if mkts else 0
        crowd_avg = (
            sum(m['crowd_brier'] for m in mkts if 'crowd_brier' in m) /
            sum(1 for m in mkts if 'crowd_brier' in m)
            if any('crowd_brier' in m for m in mkts) else None
        )
        total_rbp = sum(
            compute_rbp(m['brier_score'], m.get('crowd_brier', m['brier_score']), stage_w)
            for m in mkts
        )
        beat = sum(
            1 for m in mkts
            if 'crowd_brier' in m and m['brier_score'] < m['crowd_brier']
        )
        table.append({
            'match':      match,
            'n':          len(mkts),
            'match_rbp':  round(total_rbp, 2),
            'your_brier': round(your_avg, 3),
            'crowd_brier': round(crowd_avg, 3) if crowd_avg else None,
            'beat_crowd': beat,
        })
    return sorted(table, key=lambda r: r['match_rbp'], reverse=True)


# ─── §1.3  Cost-of-distortion check ──────────────────────────────────────────

def cost_of_distortion(deviation_pp: float, n_markets: int = 1) -> dict:
    """
    §1.3: expected RBP cost of shading by d percentage points.
    deviation_pp: |q − p| in percentage points.
    Returns cost per market and total across n_markets.
    """
    d = deviation_pp / 100.0
    cost_per = 100.0 * d ** 2
    return {
        'deviation_pp':  deviation_pp,
        'cost_per_market': round(cost_per, 3),
        'total_over_n':  round(cost_per * n_markets, 1),
        'n_markets':     n_markets,
    }
