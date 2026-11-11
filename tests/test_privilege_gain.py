"""The no-silent-privilege-gain rule: gains are either prevented or listed, never hidden."""

import pytest

from access_rat.analysis import analyse
from access_rat.design import design_roles
from access_rat.impact import HIGH, MEDIUM, compute_impact, diff_access
from access_rat.model import Params, SodRule
from access_rat.pipeline import run

from conftest import make_dataset

SENSITIVE = Params().sensitive_actions


def test_diff_detects_gain_and_loss():
    d = diff_access(frozenset({"a", "b"}), frozenset({"b", "c"}), [], SENSITIVE)
    assert d.gained == ("c",)
    assert d.lost == ("a",)
    assert d.gains_access


def test_plain_gain_is_medium_and_sensitive_gain_is_high():
    assert diff_access(frozenset(), frozenset({"doc.export"}), [], SENSITIVE).severity == MEDIUM
    assert diff_access(frozenset(), frozenset({"pay.approve"}), [], SENSITIVE).severity == HIGH


def test_gain_creating_new_sod_conflict_is_high_even_if_not_sensitive():
    rules = [SodRule("R1", "x.make", "x.check")]
    d = diff_access(frozenset({"x.make"}), frozenset({"x.make", "x.check"}), rules, ("approve",))
    assert d.new_conflicts == ("R1",)
    assert d.severity == HIGH


def test_existing_conflict_is_not_reported_as_new():
    rules = [SodRule("R1", "x.make", "x.check")]
    both = frozenset({"x.make", "x.check"})
    d = diff_access(both, both | {"x.view"}, rules, ("approve",))
    assert d.new_conflicts == ()


def test_loss_alone_is_not_a_gain():
    d = diff_access(frozenset({"a", "b"}), frozenset({"a"}), [], SENSITIVE)
    assert not d.gains_access and d.severity == ""


def test_default_policy_refuses_a_merge_that_would_give_anyone_new_access(tiny):
    res = run(tiny, Params(threshold=0.7))
    assert len(res.design.roles) == 2
    assert res.summary["impact"]["users_gaining_access"] == 0
    assert res.summary["impact"]["merges_blocked"] == 1
    assert all(not i.diff.gains_access for i in res.impacts)


def test_permissive_policy_merges_but_lists_the_user_who_gains(tiny):
    res = run(tiny, Params(threshold=0.7, max_gain_share=1.0))
    assert len(res.design.roles) == 1
    gainers = [i for i in res.impacts if i.diff.gains_access]
    assert [g.user for g in gainers] == ["a1"]
    assert gainers[0].diff.gained == ("doc.export",)
    assert gainers[0].review_required
    assert gainers[0].gained_via == (res.design.roles[0].role_id,)


def test_gain_share_limit_is_respected(tiny):
    # 1 of 4 members would gain (25%): allowed at 30%, refused at 20%.
    assert len(run(tiny, Params(threshold=0.7, max_gain_share=0.3)).design.roles) == 1
    assert len(run(tiny, Params(threshold=0.7, max_gain_share=0.2)).design.roles) == 2


def test_new_sod_conflict_inside_a_role_blocks_the_merge():
    users = {u: ("Finance", "Clerk") for u in ("u1", "u2")}
    rules = [SodRule("R1", "pay.create", "pay.approve")]
    ds = make_dataset(
        users,
        {"G1": ["u1"], "G2": ["u2"]},
        {
            "G1": ["a.1", "a.2", "a.3", "a.4", "pay.create"],
            "G2": ["a.1", "a.2", "a.3", "a.4", "pay.approve"],
        },
        rules,
    )
    p = Params(threshold=0.5, max_gain_share=1.0)
    res = run(ds, p)
    assert len(res.design.roles) == 2
    assert "R1" in res.design.blocked[0].reason


@pytest.mark.parametrize("threshold", [0.5, 0.6, 0.8, 0.9, 1.0])
def test_zero_gain_limit_means_zero_gains_on_demo_data(demo_dir, threshold):
    from access_rat.loader import load_from_directory

    ds = load_from_directory(demo_dir)
    res = run(ds, Params(threshold=threshold, max_gain_share=0.0))
    assert res.summary["impact"]["users_gaining_access"] == 0


def test_every_gain_is_flagged_for_review_on_demo_data(demo_dir):
    from access_rat.loader import load_from_directory

    ds = load_from_directory(demo_dir)
    an = analyse(ds, Params(threshold=0.7, max_gain_share=1.0))
    design = design_roles(ds, an, Params(threshold=0.7, max_gain_share=1.0))
    impacts = compute_impact(ds, an, design, Params())
    gainers = [i for i in impacts if i.diff.gains_access]
    assert gainers, "this configuration is expected to create gains on the demo data"
    for i in impacts:
        actual_gain = set(i.diff.gained) == (
            set().union(*(design.role(r).permissions for r in i.new_roles)) - an.effective[i.user]
        )
        assert actual_gain
        assert i.review_required == bool(i.diff.gained or i.diff.lost)
        assert i.diff.severity != "" or not i.diff.gained


def test_union_design_never_removes_access(demo_dir):
    from access_rat.loader import load_from_directory

    ds = load_from_directory(demo_dir)
    res = run(ds, Params(threshold=0.6, max_gain_share=1.0))
    assert res.summary["impact"]["users_losing_access"] == 0
