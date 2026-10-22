"""Stratified review sampling for theme discovery and the QA re-tag."""

import random
from collections import defaultdict
from collections.abc import Sequence

from app.models import Review


def _stratum(review: Review) -> tuple:
    return (
        review.playtime_band or "unknown",
        bool(review.written_during_early_access),
        (review.effective_language or "") == "english",
    )


def _allocate(group: Sequence[Review], target: int, rng: random.Random) -> list[Review]:
    """Pick `target` reviews from group, proportional to each stratum's size, and at least one
    from every stratum while there is room."""
    if target <= 0:
        return []
    if target >= len(group):
        return list(group)
    strata: dict[tuple, list[Review]] = defaultdict(list)
    for review in group:
        strata[_stratum(review)].append(review)
    keys = sorted(strata, key=lambda k: (-len(strata[k]), k))  # biggest strata first
    quotas = {k: target * len(strata[k]) / len(group) for k in keys}

    alloc = {k: 0 for k in keys}
    # One per stratum, biggest first, as far as the target allows.
    for k in keys[:target]:
        alloc[k] = 1
    # Then fill up to each stratum's proportional quota.
    for k in keys:
        alloc[k] = max(alloc[k], min(len(strata[k]), int(quotas[k])))
    # Trim if minimums pushed us over, taking from the biggest allocations.
    while sum(alloc.values()) > target:
        k = max(keys, key=lambda k: alloc[k])
        alloc[k] -= 1
    # Top up by largest remainder.
    order = sorted(keys, key=lambda k: quotas[k] - int(quotas[k]), reverse=True)
    while sum(alloc.values()) < target:
        progressed = False
        for k in order:
            if sum(alloc.values()) < target and alloc[k] < len(strata[k]):
                alloc[k] += 1
                progressed = True
        if not progressed:
            break

    picked: list[Review] = []
    for k in keys:
        picked.extend(rng.sample(strata[k], alloc[k]))
    return picked


def stratified_sample(
    reviews: Sequence[Review], size: int, *, seed: int, min_negative_share: float = 0.3
) -> list[Review]:
    """A sample mixing positive and negative votes, playtime bands, early access vs full release,
    and English vs other languages. Negative reviews are kept to at least `min_negative_share` of
    the sample when there are enough of them, because problems are what the team most needs to see.
    Deterministic for a given seed and review set."""
    if len(reviews) <= size:
        return sorted(reviews, key=lambda r: r.id)
    rng = random.Random(seed)
    positive = sorted((r for r in reviews if r.voted_up), key=lambda r: r.id)
    negative = sorted((r for r in reviews if not r.voted_up), key=lambda r: r.id)

    neg_target = max(round(size * len(negative) / len(reviews)), round(size * min_negative_share))
    neg_target = min(len(negative), neg_target)
    pos_target = min(len(positive), size - neg_target)
    neg_target = min(len(negative), size - pos_target)
    sample = _allocate(positive, pos_target, rng) + _allocate(negative, neg_target, rng)
    return sorted(sample, key=lambda r: r.id)
