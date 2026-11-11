"""Segregation-of-duties (SoD) detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .model import SodRule


@dataclass(frozen=True)
class Conflict:
    user: str
    rule_id: str
    perm_a: str
    perm_b: str
    groups_a: tuple[str, ...]  # groups that grant perm_a to this user
    groups_b: tuple[str, ...]  # groups that grant perm_b to this user

    @property
    def single_group(self) -> bool:
        """True when one group grants both sides (a toxic group rather than a combination)."""
        return bool(set(self.groups_a) & set(self.groups_b))


def conflicting_rules(permissions: Iterable[str], rules: Iterable[SodRule]) -> list[SodRule]:
    """Rules whose two permissions are both present, in rule order."""
    perms = set(permissions)
    return [r for r in rules if r.perm_a in perms and r.perm_b in perms]


def user_conflicts(
    user_groups: Mapping[str, Iterable[str]],
    group_perms: Mapping[str, frozenset[str]],
    rules: list[SodRule],
) -> list[Conflict]:
    """All SoD conflicts per user, sorted by user then rule, with the granting groups."""
    out: list[Conflict] = []
    for user in sorted(user_groups):
        groups = sorted(user_groups[user])
        effective: set[str] = set()
        for g in groups:
            effective |= group_perms.get(g, frozenset())
        for rule in conflicting_rules(effective, rules):
            ga = tuple(g for g in groups if rule.perm_a in group_perms.get(g, frozenset()))
            gb = tuple(g for g in groups if rule.perm_b in group_perms.get(g, frozenset()))
            out.append(Conflict(user, rule.rule_id, rule.perm_a, rule.perm_b, ga, gb))
    return out


def toxic_groups(
    group_perms: Mapping[str, frozenset[str]], rules: list[SodRule]
) -> dict[str, list[str]]:
    """Groups (or roles) that contain both sides of a rule on their own."""
    out: dict[str, list[str]] = {}
    for name in sorted(group_perms):
        hits = [r.rule_id for r in conflicting_rules(group_perms[name], rules)]
        if hits:
            out[name] = hits
    return out
