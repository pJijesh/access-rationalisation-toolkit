"""Command line interface: access-rat generate-demo | analyse."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .demo import write_demo
from .errors import ValidationError
from .loader import load_from_directory
from .model import Params
from .pipeline import run, write_outputs
from .report import render_html, render_markdown


def _unit_float(text: str) -> float:
    value = float(text)
    if not 0.0 < value <= 1.0:
        raise argparse.ArgumentTypeError("must be greater than 0 and at most 1")
    return value


def _share(text: str) -> float:
    value = float(text)
    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="access-rat",
        description="Analyse legacy access groups and propose a consolidated role model.",
    )
    p.add_argument("--version", action="version", version=f"access-rat {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate-demo", help="write a seeded, synthetic dataset")
    g.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    g.add_argument("--out", default="demo-data", help="output directory (default demo-data)")

    for name in ("analyse", "analyze"):
        a = sub.add_parser(name, help="analyse a dataset and write reports" if name == "analyse" else argparse.SUPPRESS)
        a.add_argument("--data", default="demo-data", help="directory holding the CSV files (default demo-data)")
        a.add_argument("--users", help="override path to users.csv")
        a.add_argument("--memberships", help="override path to memberships.csv")
        a.add_argument("--group-permissions", dest="group_permissions", help="override path to group_permissions.csv")
        a.add_argument("--sod-rules", dest="sod_rules", help="override path to sod_rules.csv")
        a.add_argument("--out", default="output", help="output directory (default output)")
        a.add_argument("--threshold", type=_unit_float, default=0.8, help="permission Jaccard needed to merge groups (default 0.8)")
        a.add_argument("--max-groups", type=int, default=4, help="report users holding more groups than this (default 4)")
        a.add_argument("--spread-min", type=int, default=5, help="report permissions granted by at least this many groups (default 5)")
        a.add_argument("--dominance", type=_unit_float, default=0.6, help="member share that makes a group departmental (default 0.6)")
        a.add_argument("--max-gain-share", type=_share, default=0.0,
                       help="refuse a merge that would give new access to more than this share of the role's members "
                            "(0 forbids any gain, 1 allows any; default 0, so no merge may give anyone new access)")
        a.add_argument("--sensitive-actions", help="comma-separated action names treated as sensitive when gained")
        a.add_argument("--top", type=int, default=25, help="rows shown per long list in the reports (default 25)")
        a.add_argument("--fail-on-gain", action="store_true", help="exit with status 3 if any user would gain access")
    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    written = write_demo(args.out, args.seed)
    print(f"Wrote synthetic demo data (seed {args.seed}) to {Path(args.out)}/")
    for name in sorted(written):
        print(f"  {name}")
    return 0


def _cmd_analyse(args: argparse.Namespace) -> int:
    try:
        ds = load_from_directory(args.data, args.users, args.memberships, args.group_permissions, args.sod_rules)
    except ValidationError as exc:
        print(exc.format(), file=sys.stderr)
        return 2
    base = Params()
    params = Params(
        threshold=args.threshold,
        max_groups=args.max_groups,
        spread_min=args.spread_min,
        dominance=args.dominance,
        max_gain_share=args.max_gain_share,
        sensitive_actions=tuple(s.strip() for s in args.sensitive_actions.split(",") if s.strip())
        if args.sensitive_actions
        else base.sensitive_actions,
        top=args.top,
    )
    res = run(ds, params)
    paths = write_outputs(res, args.out, render_markdown(res), render_html(res))
    s = res.summary
    b, a, imp = s["before"], s["after"], s["impact"]
    print(f"access-rat {__version__}")
    print(f"Loaded {s['inputs']['users']} users, {s['inputs']['groups']} groups, "
          f"{s['inputs']['permissions']} permissions, {s['inputs']['memberships']} memberships, {s['inputs']['sod_rules']} SoD rules")
    for w in ds.warnings:
        print(f"Note: {w}")
    print(f"Groups -> roles: {b['groups']} -> {a['roles']} ({s['reduction']['groups_removed_pct']}% fewer)")
    print(f"Retired groups: {a['groups_retired']} ({b['groups_with_no_members']} with no members, "
          f"{b['groups_with_no_permissions']} granting no permissions)")
    print(f"Average groups per user: {b['avg_groups_per_user']:.2f} -> {a['avg_roles_per_user']:.2f}")
    print(f"SoD: {b['users_with_sod_conflict']} users / {b['sod_conflict_instances']} conflicts today; "
          f"{a['users_with_sod_conflict']} users / {a['sod_conflict_instances']} after "
          f"({a['sod_conflicts_newly_introduced']} newly introduced)")
    print(f"Access changes: {imp['users_gaining_access']} users gain access "
          f"({imp['users_gaining_access_high']} HIGH), {imp['users_losing_access']} lose access, "
          f"{imp['users_unchanged']} unchanged")
    if imp["merges_blocked"]:
        print(f"Merges refused by safety rules: {imp['merges_blocked']}")
    print(f"Wrote {', '.join(p.name for p in paths)} to {Path(args.out)}/")
    if args.fail_on_gain and imp["users_gaining_access"]:
        print("Failing because users would gain access (--fail-on-gain).", file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate-demo":
        return _cmd_generate(args)
    return _cmd_analyse(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
