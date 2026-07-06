"""Regression check: reproduce every worked table in the spec from the
general-purpose functions, so drift is caught immediately.

Run: python3 -m engine.self_check   (from the repo root)
"""
from . import thresholds as th
from . import tie_trap as tt
from . import lambda_engine as le
from .poisson import poisson_cdf, poisson_sf

FAILURES = []


def check(label, got, want, tol):
    ok = abs(got - want) <= tol
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}: got {got:.2f}, want {want} (+/-{tol})")
    if not ok:
        FAILURES.append(label)


def main():
    print("== totals grid (§5.2) ==")
    for p_over, T, p_le2, p_00, p_2h_ge2 in le.TOTALS_GRID:
        check(f"T={T} P(over2.5)", poisson_sf(2, T) * 100, p_over * 100, 2)
        check(f"T={T} P(<=2)", poisson_cdf(2, T) * 100, p_le2 * 100, 2)
        check(f"T={T} P(0-0)", le.p_00(T) * 100, p_00 * 100, 1)

    print("\n== tie-trap reference table (§5.4) ==")
    for stat, (m, tie_pct, a_more_pct) in tt.REFERENCE_TABLE.items():
        check(f"{stat} tie%", tt.tie_prob(m) * 100, tie_pct, 0.5)
        check(f"{stat} A-more% (even)", tt.p_a_more(m, m) * 100, a_more_pct, 1.5)

    print("\n== card/corner/SOT/offside tail tables (§5.5) ==")
    for lam, p_ge4, p_2h_ge2 in th.CARDS_TABLE:
        check(f"cards lam={lam} P(>=4)", th.p_cards_at_least(4, lam) * 100, p_ge4, 1)
        check(f"cards lam={lam} P(2H>=2)", th.p_cards_2h_at_least(2, lam) * 100, p_2h_ge2, 1)
    for lam, p_ge5 in th.CORNERS_GE5_TABLE.items():
        check(f"corners lam={lam} P(>=5)", th.p_corners_at_least(5, lam) * 100, p_ge5, 1)
    for lam, p_ge2 in th.SOT_GE2_TABLE.items():
        check(f"SOT lam={lam} P(>=2)", th.p_sot_at_least(2, lam) * 100, p_ge2, 1)
    for lam, p_ge2 in th.OFFSIDES_GE2_TABLE.items():
        check(f"offsides lam={lam} P(>=2)", th.p_offsides_at_least(2, lam) * 100, p_ge2, 1)

    print("\n== HT-tied / HT-both-SOT (§5.5) ==")
    for label, T, pct in th.HT_TIED_TABLE:
        if T is not None:
            check(f"HT-tied {label}", th.ht_tied(T / 2, T / 2) * 100, pct, 1)
    for (sot_a, sot_b), pct in th.HT_BOTH_SOT_TABLE.items():
        check(f"HT-both-SOT {sot_a}/{sot_b}", th.ht_both_sot(sot_a, sot_b) * 100, pct, 2)

    print("\n== BTTS grid (§5.2) ==")
    splits = {
        "even_1.35_1.35": (1.35, 1.35), "moderate_fav_1.65_1.05": (1.65, 1.05),
        "strong_2.0_0.75": (2.0, 0.75), "heavy_2.4_0.55": (2.4, 0.55),
    }
    for label, (btts, p11, btts3) in le.BTTS_GRID.items():
        la, lb = splits[label]
        check(f"{label} BTTS", le.p_btts(la, lb) * 100, btts * 100, 1)
        check(f"{label} P(1-1)", le.p_11(la, lb) * 100, p11 * 100, 1)
        check(f"{label} BTTS^3+", le.p_btts_and_3plus(la, lb) * 100, btts3 * 100, 1)

    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nAll checks passed.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
