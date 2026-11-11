"""Shared helpers: build small in-memory datasets without touching the filesystem."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from access_rat.model import Dataset, SodRule  # noqa: E402


def make_dataset(users, memberships, group_perms, rules=()):
    """users: {user: (dept, title)}; memberships: {group: [users]}; group_perms: {group: [perms]}."""
    return Dataset(
        users=dict(sorted(users.items())),
        group_members={g: frozenset(m) for g, m in sorted(memberships.items())},
        group_perms={g: frozenset(p) for g, p in sorted(group_perms.items())},
        sod_rules=[SodRule(*r) if not isinstance(r, SodRule) else r for r in rules],
    )


@pytest.fixture
def tiny():
    """Four Operations users. G_SMALL is a strict subset of G_BIG (Jaccard 0.8).

    a1 only has G_SMALL, so merging the two groups would give a1 'doc.export'.
    """
    users = {u: ("Operations", "Operator") for u in ("a1", "a2", "a3", "a4")}
    memberships = {"G_SMALL": ["a1"], "G_BIG": ["a2", "a3", "a4"]}
    group_perms = {
        "G_SMALL": ["doc.view", "doc.edit", "job.view", "job.edit"],
        "G_BIG": ["doc.view", "doc.edit", "job.view", "job.edit", "doc.export"],
    }
    return make_dataset(users, memberships, group_perms)


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory):
    from access_rat.demo import write_demo

    d = tmp_path_factory.mktemp("demo")
    write_demo(d, seed=42)
    return d
