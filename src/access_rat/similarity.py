"""Set similarity measures."""

from __future__ import annotations

from typing import Iterable, Mapping


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Jaccard similarity |A and B| / |A or B|.

    Two empty sets return 0.0 rather than 1.0: two groups that grant nothing
    are not evidence of a meaningful duplicate.
    """
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def containment(a: Iterable[str], b: Iterable[str]) -> float:
    """Share of A that is also in B: |A and B| / |A|. Returns 0.0 for empty A."""
    sa, sb = set(a), set(b)
    if not sa:
        return 0.0
    return len(sa & sb) / len(sa)


def pairwise_jaccard(named_sets: Mapping[str, Iterable[str]]) -> dict[tuple[str, str], float]:
    """Jaccard similarity for every unordered pair, keyed with the names in sorted order."""
    names = sorted(named_sets)
    frozen = {n: frozenset(named_sets[n]) for n in names}
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            out[(a, b)] = jaccard(frozen[a], frozen[b])
    return out
