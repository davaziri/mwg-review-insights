"""Quality check: the analysis model re-tags a random sample and we measure agreement per theme."""

import math
import random
from collections.abc import Iterable, Sequence

from app.config import Settings
from app.models import Theme


def qa_count(n_tagged: int, settings: Settings) -> int:
    """5% of the reviews tagged in a run, but at least qa_min_reviews (or all if fewer)."""
    if n_tagged <= 0:
        return 0
    return min(n_tagged, max(math.ceil(n_tagged * settings.qa_sample_rate), settings.qa_min_reviews))


def choose_qa_sample(review_ids: Sequence[int], count: int, seed: int) -> list[int]:
    return sorted(random.Random(seed).sample(list(review_ids), count))


def kappa(both: int, primary_only: int, qa_only: int, neither: int) -> float | None:
    """Cohen's kappa for theme presence. None when it is undefined (no variation at all)."""
    n = both + primary_only + qa_only + neither
    if n == 0:
        return None
    observed = (both + neither) / n
    p_primary = (both + primary_only) / n
    p_qa = (both + qa_only) / n
    expected = p_primary * p_qa + (1 - p_primary) * (1 - p_qa)
    if expected >= 1:
        return None
    return (observed - expected) / (1 - expected)


def agreement(themes: Sequence[Theme], rows: Iterable[tuple[int, bool, str | None, bool, str | None]]) -> dict:
    """rows: (theme_id, primary_present, primary_sentiment, qa_present, qa_sentiment) per review x theme."""
    per = {t.id: {"both": 0, "primary_only": 0, "qa_only": 0, "neither": 0, "same_sentiment": 0} for t in themes}
    for theme_id, p, ps, q, qs in rows:
        c = per.get(theme_id)
        if c is None:
            continue
        if p and q:
            c["both"] += 1
            c["same_sentiment"] += int(ps == qs)
        elif p:
            c["primary_only"] += 1
        elif q:
            c["qa_only"] += 1
        else:
            c["neither"] += 1

    out_themes = {}
    totals = {"both": 0, "primary_only": 0, "qa_only": 0, "neither": 0, "same_sentiment": 0}
    kappas = []
    for t in themes:
        c = per[t.id]
        n = c["both"] + c["primary_only"] + c["qa_only"] + c["neither"]
        k = kappa(c["both"], c["primary_only"], c["qa_only"], c["neither"])
        if k is not None:
            kappas.append(k)
        for key in totals:
            totals[key] += c[key]
        out_themes[t.key] = {
            "name": t.name,
            "reviews": n,
            **{key: c[key] for key in ("both", "primary_only", "qa_only", "neither")},
            "presence_agreement": (c["both"] + c["neither"]) / n if n else None,
            "kappa": k,
            "sentiment_agreement": c["same_sentiment"] / c["both"] if c["both"] else None,
        }
    cells = sum(totals[k] for k in ("both", "primary_only", "qa_only", "neither"))
    return {
        "themes": out_themes,
        "overall": {
            "cells": cells,
            "presence_agreement": (totals["both"] + totals["neither"]) / cells if cells else None,
            "mean_kappa": sum(kappas) / len(kappas) if kappas else None,
            "sentiment_agreement": totals["same_sentiment"] / totals["both"] if totals["both"] else None,
        },
    }


def overall_agreement(pairs: Iterable[tuple[str, str]]) -> dict:
    """pairs: (primary overall impression, QA overall impression) per re-checked review."""
    pairs = list(pairs)
    same = sum(1 for p, q in pairs if p == q)
    differ: dict[str, int] = {}
    for p, q in pairs:
        if p != q:
            differ[f"{p}>{q}"] = differ.get(f"{p}>{q}", 0) + 1
    return {"reviews": len(pairs), "agreement": same / len(pairs) if pairs else None, "differences": differ}
