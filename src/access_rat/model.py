"""Plain data containers shared across modules."""

from __future__ import annotations

from dataclasses import dataclass, field


def is_sensitive(permission: str, sensitive_actions: tuple[str, ...]) -> bool:
    """True when the final segment of the permission name is a sensitive action (heuristic)."""
    return permission.rsplit(".", 1)[-1] in sensitive_actions


@dataclass(frozen=True)
class SodRule:
    """A segregation-of-duties rule: one person should not hold both permissions."""

    rule_id: str
    perm_a: str
    perm_b: str
    description: str = ""


@dataclass
class Dataset:
    """Validated input data. Every collection is deterministic to iterate."""

    users: dict[str, tuple[str, str]]  # user -> (department, job_title)
    group_members: dict[str, frozenset[str]]  # group -> users
    group_perms: dict[str, frozenset[str]]  # group -> permissions
    sod_rules: list[SodRule]
    input_hashes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def groups(self) -> list[str]:
        return sorted(set(self.group_members) | set(self.group_perms))

    def members_of(self, group: str) -> frozenset[str]:
        return self.group_members.get(group, frozenset())

    def perms_of(self, group: str) -> frozenset[str]:
        return self.group_perms.get(group, frozenset())

    def department_of(self, user: str) -> str:
        return self.users[user][0]

    @property
    def user_groups(self) -> dict[str, frozenset[str]]:
        acc: dict[str, set[str]] = {u: set() for u in self.users}
        for group, members in self.group_members.items():
            for user in members:
                acc[user].add(group)
        return {u: frozenset(g) for u, g in sorted(acc.items())}


@dataclass(frozen=True)
class Params:
    """Tunable analysis parameters. All have conservative defaults."""

    threshold: float = 0.8  # permission-set Jaccard needed to merge groups
    max_groups: int = 4  # users above this many groups are reported as excess
    spread_min: int = 5  # permissions granted by at least this many groups are reported
    dominance: float = 0.6  # share of members from one department to call a group departmental
    max_gain_share: float = 0.0  # a merge may give new access to at most this share of the role's members
    sensitive_actions: tuple[str, ...] = (
        "approve",
        "release",
        "delete",
        "void",
        "admin",
        "adjust",
        "reset_password",
        "edit_bank_details",
        "set_credit_limit",
    )
    top: int = 25  # rows shown per long list in the Markdown and HTML reports
