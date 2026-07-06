"""Quick command-line entry points so a session doesn't have to hand-roll
python one-liners every time. Run as `python3 -m engine.cli <subcommand> ...`
from the repo root.
"""
import argparse
import json
import sys

from . import devig as dv
from . import lambda_engine as le
from . import tie_trap as tt
from . import thresholds as th
from . import player_props as pp
from . import rbp as rbp_mod
from . import mc_batch as mc


def cmd_devig(args):
    odds = [float(x) for x in args.odds]
    print(json.dumps(dv.devig(odds), indent=2))


def cmd_totals(args):
    T = le.interpolate_T(args.p_over25)
    print(json.dumps({
        "T": T,
        "p_over25": le.p_over(2, T),
        "p_over15": le.p_over(1, T),
        "p_00": le.p_00(T),
        "p_le2": le.p_at_most(2, T),
    }, indent=2))


def cmd_1x2(args):
    print(json.dumps(le.poisson_1x2(args.lam_a, args.lam_b), indent=2))


def cmd_split(args):
    print(json.dumps(le.solve_split(args.T, args.target_home, args.target_away), indent=2))


def cmd_tie(args):
    if args.m_b is None:
        args.m_b = args.m_a
    print(json.dumps(tt.skewed_split(args.m_a, args.m_b), indent=2))


def cmd_threshold(args):
    fn = {
        "cards": th.p_cards_at_least, "corners": th.p_corners_at_least,
        "sot": th.p_sot_at_least, "offsides": th.p_offsides_at_least,
    }[args.kind]
    print(json.dumps({"p": fn(args.k, args.lam)}, indent=2))


def cmd_ht_tied(args):
    print(json.dumps({"p": th.ht_tied(args.lam_a, args.lam_b)}, indent=2))


def cmd_driver_gate(args):
    print(json.dumps(pp.driver_gate(args.p, args.has_driver), indent=2))


def cmd_rbp(args):
    print(json.dumps({"rbp": rbp_mod.rbp(args.crowd_brier, args.your_brier, args.stage_weight)}, indent=2))


def cmd_decode(args):
    print(json.dumps({"outcome": rbp_mod.decode_outcome(args.p, args.brier)}, indent=2))


def cmd_mc(args):
    with open(args.file) as f:
        matches = json.load(f)
    print(json.dumps(mc.batch_mc(matches), indent=2))


def build_parser():
    p = argparse.ArgumentParser(prog="engine.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("devig", help="devig a set of decimal odds")
    s.add_argument("odds", nargs="+")
    s.set_defaults(func=cmd_devig)

    s = sub.add_parser("totals", help="derive T + goal probs from P(over2.5)")
    s.add_argument("p_over25", type=float)
    s.set_defaults(func=cmd_totals)

    s = sub.add_parser("1x2", help="exact Poisson 1X2 from two team lambdas")
    s.add_argument("lam_a", type=float)
    s.add_argument("lam_b", type=float)
    s.set_defaults(func=cmd_1x2)

    s = sub.add_parser("split", help="solve lambda split to match a devigged 1X2")
    s.add_argument("T", type=float)
    s.add_argument("target_home", type=float)
    s.add_argument("target_away", type=float)
    s.set_defaults(func=cmd_split)

    s = sub.add_parser("tie", help="tie-trap: exact tie/more probs for two means")
    s.add_argument("m_a", type=float)
    s.add_argument("m_b", type=float, nargs="?", default=None)
    s.set_defaults(func=cmd_tie)

    s = sub.add_parser("threshold", help="Poisson P(>=k) for cards/corners/sot/offsides")
    s.add_argument("kind", choices=["cards", "corners", "sot", "offsides"])
    s.add_argument("k", type=int)
    s.add_argument("lam", type=float)
    s.set_defaults(func=cmd_threshold)

    s = sub.add_parser("ht-tied", help="HT-tied probability from two HT lambdas")
    s.add_argument("lam_a", type=float)
    s.add_argument("lam_b", type=float)
    s.set_defaults(func=cmd_ht_tied)

    s = sub.add_parser("driver-gate", help="§5.6 L10 driver gate check")
    s.add_argument("p", type=float)
    s.add_argument("--has-driver", dest="has_driver", action="store_true")
    s.set_defaults(func=cmd_driver_gate)

    s = sub.add_parser("rbp", help="compute RBP for a market")
    s.add_argument("crowd_brier", type=float)
    s.add_argument("your_brier", type=float)
    s.add_argument("--stage-weight", type=int, default=1)
    s.set_defaults(func=cmd_rbp)

    s = sub.add_parser("decode", help="§9.2 decode outcome from p + brier")
    s.add_argument("p", type=float)
    s.add_argument("brier", type=float)
    s.set_defaults(func=cmd_decode)

    s = sub.add_parser("mc", help="run batched MC over a JSON matches file (§5.11 L8)")
    s.add_argument("file")
    s.set_defaults(func=cmd_mc)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
