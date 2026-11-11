from access_rat.model import SodRule
from access_rat.sod import conflicting_rules, toxic_groups, user_conflicts

RULES = [SodRule("R1", "pay.create", "pay.approve"), SodRule("R2", "sup.create", "pay.approve")]
GP = {
    "G_MAKER": frozenset({"pay.create", "pay.view"}),
    "G_CHECKER": frozenset({"pay.approve"}),
    "G_SUPPLIER": frozenset({"sup.create"}),
    "G_BOTH": frozenset({"pay.create", "pay.approve"}),
}


def test_pair_detected_across_two_groups():
    found = user_conflicts({"u1": ["G_MAKER", "G_CHECKER"]}, GP, RULES)
    assert [c.rule_id for c in found] == ["R1"]
    assert found[0].groups_a == ("G_MAKER",)
    assert found[0].groups_b == ("G_CHECKER",)
    assert not found[0].single_group


def test_no_conflict_when_only_one_side_held():
    assert user_conflicts({"u1": ["G_MAKER"], "u2": ["G_CHECKER"]}, GP, RULES) == []


def test_rule_direction_does_not_matter():
    reversed_rule = [SodRule("R9", "pay.approve", "pay.create")]
    assert len(user_conflicts({"u1": ["G_MAKER", "G_CHECKER"]}, GP, reversed_rule)) == 1


def test_one_user_can_breach_several_rules():
    found = user_conflicts({"u1": ["G_MAKER", "G_CHECKER", "G_SUPPLIER"]}, GP, RULES)
    assert [c.rule_id for c in found] == ["R1", "R2"]


def test_single_group_conflict_is_labelled():
    found = user_conflicts({"u1": ["G_BOTH"]}, GP, RULES)
    assert len(found) == 1 and found[0].single_group


def test_toxic_groups_found():
    assert toxic_groups(GP, RULES) == {"G_BOTH": ["R1", "R2"][:1]}


def test_conflicting_rules_on_plain_sets():
    assert conflicting_rules({"pay.create", "pay.approve"}, RULES) == [RULES[0]]
    assert conflicting_rules(set(), RULES) == []


def test_results_sorted_by_user():
    found = user_conflicts({"b": ["G_BOTH"], "a": ["G_BOTH"]}, GP, RULES)
    assert [c.user for c in found] == ["a", "b"]
