"""Propose a consolidated role model from the legacy groups.

Method
------
1. Retire groups with no members, and groups that grant no permissions.
2. Cluster the remaining groups by permission-set Jaccard similarity using
   complete linkage (every pair in a cluster must reach the threshold, which
   prevents chaining of loosely related groups).
3. Only merge groups that share a dominant department (or have identical
   permission sets), so roles follow the department patterns in the data.
4. Refuse any merge that would create a role holding both sides of a
   segregation-of-duties rule that no source group already held.
5. Refuse any merge that would give new access to more than `max_gain_share`
   of the merged role's members (0 forbids any gain). Smaller gains are allowed
   but every user who gains access is listed for review.

A merged role grants the union of its source groups' permissions. The model
therefore never removes access, and any gain is explicit and reviewable.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analysis import MIXED, Analysis, dominant_department
from .model import Dataset, Params, is_sensitive
from .sod import conflicting_rules

RETIRE_NO_MEMBERS = "retire (no members)"
RETIRE_NO_PERMS = "retire (grants no permissions)"
RETAIN = "retain"
MERGE_IDENTICAL = "merge (identical permissions)"
MERGE_SIMILAR = "merge (similar permissions)"


@dataclass
class Role:
    role_id: str
    name: str
    department: str
    groups: tuple[str, ...]
    permissions: frozenset[str]
    members: frozenset[str]
    min_similarity: float  # weakest pairwise permission Jaccard inside the role (1.0 for one group)

    @property
    def action(self) -> str:
        if len(self.groups) == 1:
            return RETAIN
        return MERGE_IDENTICAL if self.min_similarity >= 1.0 else MERGE_SIMILAR


@dataclass
class BlockedMerge:
    groups_a: tuple[str, ...]
    groups_b: tuple[str, ...]
    similarity: float
    reason: str


@dataclass
class Design:
    roles: list[Role]
    group_to_role: dict[str, str]  # only for groups that map to a role
    retired: dict[str, str]  # group -> reason
    blocked: list[BlockedMerge] = field(default_factory=list)

    def role(self, role_id: str) -> Role:
        return next(r for r in self.roles if r.role_id == role_id)


def department_codes(departments: list[str]) -> dict[str, str]:
    """Shortest unique upper-case prefix (at least 3 letters) for each department."""
    names = sorted(set(departments))
    codes: dict[str, str] = {}
    for n in names:
        letters = "".join(ch for ch in n.upper() if ch.isalnum())
        length = 3
        while length < len(letters) and any(
            o != n and "".join(c for c in o.upper() if c.isalnum()).startswith(letters[:length])
            for o in names
        ):
            length += 1
        codes[n] = letters[:length]
    codes[MIXED] = "MIX"
    return codes


def _role_title(
    department: str,
    permissions: frozenset[str],
    prevalence: Counter,
    sensitive_actions: tuple[str, ...],
) -> str:
    """Generated label: department plus the role's most distinctive permission.

    Distinctive means held by the fewest proposed roles; ties prefer a sensitive
    action, then alphabetical order. Business owners are expected to rename roles.
    """
    signature = min(
        permissions,
        key=lambda p: (prevalence[p], 0 if is_sensitive(p, sensitive_actions) else 1, p),
    )
    label = "Cross-functional" if department == MIXED else department
    extra = len(permissions) - 1
    return f"{label} - {signature}" + (f" (+{extra})" if extra else "")


def design_roles(ds: Dataset, an: Analysis, params: Params) -> Design:
    dept_of = {u: d for u, (d, _t) in ds.users.items()}
    retired: dict[str, str] = {}
    active: list[str] = []
    for g in ds.groups:
        if not ds.members_of(g):
            retired[g] = RETIRE_NO_MEMBERS
        elif not ds.perms_of(g):
            retired[g] = RETIRE_NO_PERMS
        else:
            active.append(g)

    dominant = {g: an.group_stats[g].dominant_dept for g in active}

    def sim(a: str, b: str) -> float:
        return an.all_pair_perm_sim[(a, b) if a < b else (b, a)]

    veto_cache: dict[tuple[str, ...], str | None] = {}

    def veto(cluster: tuple[str, ...]) -> str | None:
        key = tuple(sorted(cluster))
        if key in veto_cache:
            return veto_cache[key]
        reason: str | None = None
        union: set[str] = set()
        for g in key:
            union |= ds.perms_of(g)
        for rule in conflicting_rules(union, ds.sod_rules):
            if not any(rule in conflicting_rules(ds.perms_of(g), ds.sod_rules) for g in key):
                reason = f"merged role would combine the conflicting pair in {rule.rule_id}"
                break
        if reason is None:
            affected: set[str] = set()
            for g in key:
                affected |= ds.members_of(g)
            gainers = sum(1 for u in affected if union - an.effective[u])
            if gainers and gainers / len(affected) > params.max_gain_share:
                reason = (
                    f"merged role would give new access to {gainers} of {len(affected)} members "
                    f"({100 * gainers / len(affected):.0f}%), above the {100 * params.max_gain_share:.0f}% limit"
                )
        veto_cache[key] = reason
        return reason

    clusters: list[tuple[str, ...]] = [(g,) for g in active]
    blocked: dict[tuple[tuple[str, ...], tuple[str, ...]], tuple[float, str]] = {}
    while True:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                x, y = clusters[i], clusters[j]
                link = min(sim(a, b) for a in x for b in y)
                if link < params.threshold:
                    continue
                if not all(dominant[a] == dominant[b] or sim(a, b) >= 1.0 for a in x for b in y):
                    continue
                reason = veto(x + y)
                if reason:
                    blocked[(x, y)] = (link, reason)
                    continue
                cand = (-link, x, y)
                if best is None or cand < best:
                    best = cand
        if best is None:
            break
        _neg, x, y = best
        merged = tuple(sorted(x + y))
        clusters = sorted([c for c in clusters if c not in (x, y)] + [merged])

    final = set(clusters)
    blocked_list = [
        BlockedMerge(x, y, link, reason)
        for (x, y), (link, reason) in sorted(blocked.items())
        if x in final and y in final
    ]

    # Build roles, then number them per department code.
    drafts = []
    for cluster in clusters:
        perms: set[str] = set()
        members: set[str] = set()
        for g in cluster:
            perms |= ds.perms_of(g)
            members |= ds.members_of(g)
        dept, _share = dominant_department(sorted(members), dept_of, params.dominance)
        min_sim = 1.0 if len(cluster) == 1 else min(
            sim(a, b) for i, a in enumerate(cluster) for b in cluster[i + 1 :]
        )
        drafts.append((dept, cluster, frozenset(perms), frozenset(members), min_sim))

    codes = department_codes([d for d, *_ in drafts if d != MIXED] + list(set(dept_of.values())))
    drafts.sort(key=lambda d: (codes[d[0]], -len(d[3]), d[1][0]))
    counters: Counter[str] = Counter()
    prevalence: Counter[str] = Counter(p for d in drafts for p in d[2])
    roles: list[Role] = []
    group_to_role: dict[str, str] = {}
    for dept, cluster, perms, members, min_sim in drafts:
        code = codes[dept]
        counters[code] += 1
        role_id = f"ROLE-{code}-{counters[code]:02d}"
        roles.append(Role(role_id, _role_title(dept, perms, prevalence, params.sensitive_actions), dept, cluster, perms, members, min_sim))
        for g in cluster:
            group_to_role[g] = role_id

    return Design(roles=roles, group_to_role=group_to_role, retired=retired, blocked=blocked_list)
