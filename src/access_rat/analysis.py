"""Descriptive analysis of the current (legacy) access model."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .model import Dataset, Params
from .similarity import jaccard, pairwise_jaccard
from .sod import Conflict, toxic_groups, user_conflicts

MIXED = "Mixed"
NONE = "(none)"


def dominant_department(
    users: Iterable[str], dept_of: Mapping[str, str], dominance: float
) -> tuple[str, float]:
    """Department supplying at least `dominance` of the users, else "Mixed".

    Returns (label, share_of_largest_department). Ties break alphabetically so the
    result is deterministic. An empty collection returns ("(none)", 0.0).
    """
    counts = Counter(dept_of[u] for u in users)
    total = sum(counts.values())
    if not total:
        return NONE, 0.0
    top_dept, top_count = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    share = top_count / total
    return (top_dept if share >= dominance else MIXED), share


@dataclass
class GroupStat:
    name: str
    members: int
    permissions: int
    dominant_dept: str
    dominant_share: float
    flags: list[str] = field(default_factory=list)
    redundant_memberships: int = 0


@dataclass
class PairStat:
    group_a: str
    group_b: str
    perm_jaccard: float
    member_jaccard: float
    kind: str  # identical permissions | near-identical permissions | overlapping membership
    note: str = ""


@dataclass
class Analysis:
    effective: dict[str, frozenset[str]]
    group_stats: dict[str, GroupStat]
    pairs: list[PairStat]
    empty_groups: list[str]
    no_permission_groups: list[str]
    excess_users: list[tuple[str, int]]
    perm_spread: list[tuple[str, int, int]]  # permission, groups granting it, users holding it
    conflicts: list[Conflict]
    toxic_groups: dict[str, list[str]]
    redundant: list[tuple[str, str]]  # (user, group): removing the membership changes nothing
    groups_per_user: dict[str, int]
    all_pair_perm_sim: dict[tuple[str, str], float]


def effective_permissions(
    user_groups: dict[str, frozenset[str]], group_perms: dict[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    out = {}
    for user, groups in sorted(user_groups.items()):
        acc: set[str] = set()
        for g in groups:
            acc |= group_perms.get(g, frozenset())
        out[user] = frozenset(acc)
    return out


def analyse(ds: Dataset, params: Params) -> Analysis:
    user_groups = ds.user_groups
    group_perms = {g: ds.perms_of(g) for g in ds.groups}
    effective = effective_permissions(user_groups, group_perms)
    dept_of = {u: d for u, (d, _t) in ds.users.items()}

    # Redundant memberships: dropping the membership leaves the user's access unchanged.
    redundant: list[tuple[str, str]] = []
    for user, groups in user_groups.items():
        for g in sorted(groups):
            without: set[str] = set()
            for other in groups:
                if other != g:
                    without |= group_perms[other]
            if frozenset(without) == effective[user]:
                redundant.append((user, g))
    redundant_by_group = Counter(g for _u, g in redundant)

    stats: dict[str, GroupStat] = {}
    empty, no_perm = [], []
    for g in ds.groups:
        members = ds.members_of(g)
        dom, share = dominant_department(sorted(members), dept_of, params.dominance)
        flags: list[str] = []
        if not members:
            flags.append("no members")
            empty.append(g)
        if not group_perms[g]:
            flags.append("no permissions")
            no_perm.append(g)
        stats[g] = GroupStat(g, len(members), len(group_perms[g]), dom, share, flags, redundant_by_group.get(g, 0))
        if members and redundant_by_group.get(g, 0) == len(members):
            stats[g].flags.append("redundant for all members")

    # Pairwise similarity over groups that have both members and permissions.
    live = [g for g in ds.groups if ds.members_of(g) and group_perms[g]]
    perm_sim = pairwise_jaccard({g: group_perms[g] for g in live})
    pairs: list[PairStat] = []
    for (a, b), ps in perm_sim.items():
        ms = jaccard(ds.members_of(a), ds.members_of(b))
        if ps < params.threshold and ms < params.threshold:
            continue
        if ps >= 1.0:
            kind = "identical permissions"
        elif ps >= params.threshold:
            kind = "near-identical permissions"
        else:
            kind = "overlapping membership"
        note = ""
        pa, pb = group_perms[a], group_perms[b]
        if pa < pb:
            note = f"{a} is a strict subset of {b}"
        elif pb < pa:
            note = f"{b} is a strict subset of {a}"
        elif ps >= 1.0:
            note = "same permission set"
        pairs.append(PairStat(a, b, ps, ms, kind, note))
    pairs.sort(key=lambda p: (-p.perm_jaccard, -p.member_jaccard, p.group_a, p.group_b))

    groups_per_user = {u: len(gs) for u, gs in user_groups.items()}
    excess = sorted(
        ((u, n) for u, n in groups_per_user.items() if n > params.max_groups),
        key=lambda x: (-x[1], x[0]),
    )

    perm_groups: Counter[str] = Counter()
    for g in ds.groups:
        for p in group_perms[g]:
            perm_groups[p] += 1
    perm_users: Counter[str] = Counter()
    for perms in effective.values():
        for p in perms:
            perm_users[p] += 1
    spread = sorted(
        ((p, n, perm_users.get(p, 0)) for p, n in perm_groups.items() if n >= params.spread_min),
        key=lambda x: (-x[1], -x[2], x[0]),
    )

    return Analysis(
        effective=effective,
        group_stats=stats,
        pairs=pairs,
        empty_groups=empty,
        no_permission_groups=no_perm,
        excess_users=excess,
        perm_spread=spread,
        conflicts=user_conflicts(user_groups, group_perms, ds.sod_rules),
        toxic_groups=toxic_groups({g: p for g, p in group_perms.items() if p}, ds.sod_rules),
        redundant=redundant,
        groups_per_user=groups_per_user,
        all_pair_perm_sim=perm_sim,
    )

