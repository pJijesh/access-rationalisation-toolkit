"""Per-user impact of a proposed role model, including the no-silent-gain rule."""

from __future__ import annotations

from dataclasses import dataclass

from .analysis import Analysis
from .design import Design
from .model import Dataset, Params, SodRule, is_sensitive
from .sod import conflicting_rules

HIGH = "HIGH"
MEDIUM = "MEDIUM"
NONE = ""


@dataclass(frozen=True)
class AccessDiff:
    gained: tuple[str, ...]
    lost: tuple[str, ...]
    new_conflicts: tuple[str, ...]  # rule ids that the user does not breach today but would after
    severity: str

    @property
    def gains_access(self) -> bool:
        return bool(self.gained)


def diff_access(
    old: frozenset[str],
    new: frozenset[str],
    rules: list[SodRule],
    sensitive_actions: tuple[str, ...],
) -> AccessDiff:
    """Compare effective permissions before and after.

    Severity: HIGH when the user would gain a permission that creates a new SoD
    conflict or carries a sensitive action; MEDIUM for any other gain; empty when
    nothing is gained. Losses are reported but do not raise severity here: a loss
    is an operational risk, a gain is a least-privilege regression.
    """
    gained = tuple(sorted(new - old))
    lost = tuple(sorted(old - new))
    before = {r.rule_id for r in conflicting_rules(old, rules)}
    after = {r.rule_id for r in conflicting_rules(new, rules)}
    new_conflicts = tuple(sorted(after - before))
    if not gained:
        severity = NONE
    elif new_conflicts or any(is_sensitive(p, sensitive_actions) for p in gained):
        severity = HIGH
    else:
        severity = MEDIUM
    return AccessDiff(gained, lost, new_conflicts, severity)


@dataclass
class UserImpact:
    user: str
    department: str
    job_title: str
    old_groups: tuple[str, ...]
    new_roles: tuple[str, ...]
    old_permission_count: int
    new_permission_count: int
    diff: AccessDiff
    gained_via: tuple[str, ...]  # roles that supply at least one gained permission
    sod_before: tuple[str, ...]
    sod_after: tuple[str, ...]

    @property
    def review_required(self) -> bool:
        return self.diff.gains_access or bool(self.diff.lost)


def compute_impact(ds: Dataset, an: Analysis, design: Design, params: Params) -> list[UserImpact]:
    role_perms = {r.role_id: r.permissions for r in design.roles}
    out: list[UserImpact] = []
    for user, (dept, title) in ds.users.items():
        old_groups = tuple(sorted(ds.user_groups[user]))
        new_roles = tuple(sorted({design.group_to_role[g] for g in old_groups if g in design.group_to_role}))
        new_perms: set[str] = set()
        for r in new_roles:
            new_perms |= role_perms[r]
        old = an.effective[user]
        diff = diff_access(old, frozenset(new_perms), ds.sod_rules, params.sensitive_actions)
        gained_set = set(diff.gained)
        via = tuple(r for r in new_roles if role_perms[r] & gained_set)
        out.append(
            UserImpact(
                user=user,
                department=dept,
                job_title=title,
                old_groups=old_groups,
                new_roles=new_roles,
                old_permission_count=len(old),
                new_permission_count=len(new_perms),
                diff=diff,
                gained_via=via,
                sod_before=tuple(r.rule_id for r in conflicting_rules(old, ds.sod_rules)),
                sod_after=tuple(r.rule_id for r in conflicting_rules(new_perms, ds.sod_rules)),
            )
        )
    return out
