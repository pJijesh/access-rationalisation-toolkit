import pytest

from access_rat.similarity import containment, jaccard, pairwise_jaccard


def test_identical_sets_are_one():
    assert jaccard({"a", "b"}, {"b", "a"}) == 1.0


def test_disjoint_sets_are_zero():
    assert jaccard({"a"}, {"b"}) == 0.0


def test_partial_overlap_value():
    # intersection 2, union 4
    assert jaccard({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)


def test_one_empty_set_is_zero():
    assert jaccard(set(), {"a"}) == 0.0


def test_two_empty_sets_are_not_called_duplicates():
    assert jaccard(set(), set()) == 0.0


def test_symmetry_and_iterable_inputs():
    assert jaccard(["a", "b", "b"], ("b", "c")) == jaccard(("b", "c"), ["a", "b"])


def test_containment_is_directional():
    assert containment({"a"}, {"a", "b"}) == 1.0
    assert containment({"a", "b"}, {"a"}) == 0.5
    assert containment(set(), {"a"}) == 0.0


def test_pairwise_keys_are_sorted_and_complete():
    sims = pairwise_jaccard({"z": {"x"}, "a": {"x"}, "m": {"y"}})
    assert set(sims) == {("a", "m"), ("a", "z"), ("m", "z")}
    assert sims[("a", "z")] == 1.0
    assert sims[("a", "m")] == 0.0
