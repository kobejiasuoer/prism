"""Sample matching for historical edge engine.

Finds historically similar (code, date) samples based on bucketed feature similarity.
"""

from __future__ import annotations

from typing import Any


def compute_similarity(candidate_features: dict[str, str | None], sample_features: dict[str, str | None]) -> float:
    """Compute similarity between two feature vectors (bucketed).

    Similarity = (# features matching within 1 bucket) / (# non-None features in both)

    Args:
        candidate_features: Bucketed features (e.g., {"pe_ttm": "Q2", "return_5d": "Q4", ...})
        sample_features: Bucketed features from historical sample

    Returns:
        Similarity score in [0.0, 1.0], or 0.0 if no overlapping non-None features
    """
    # Find keys present and non-None in both
    common_keys = set(candidate_features.keys()) & set(sample_features.keys())
    common_keys = {k for k in common_keys if candidate_features[k] is not None and sample_features[k] is not None}

    if not common_keys:
        return 0.0

    matches = 0
    for key in common_keys:
        cand_val = candidate_features[key]
        samp_val = sample_features[key]

        # For quintile buckets (Q1-Q5), allow within-1-bucket match
        if _is_quintile_value(cand_val) and _is_quintile_value(samp_val):
            cand_q = int(cand_val[1])  # Extract "2" from "Q2"
            samp_q = int(samp_val[1])
            if abs(cand_q - samp_q) <= 1:
                matches += 1
        else:
            # Exact match for categorical/binary features
            if cand_val == samp_val:
                matches += 1

    return matches / len(common_keys)


def _is_quintile_value(value: str | None) -> bool:
    """Check if value is a quintile bucket (Q1-Q5)."""
    if not isinstance(value, str) or len(value) != 2:
        return False
    return value[0] == "Q" and value[1] in "12345"


def match_similar_samples(
    candidate_features: dict[str, str | None],
    all_samples: list[tuple[str, str, dict[str, str | None], dict[str, Any]]],
    threshold: float = 0.5,
    max_matches: int = 100,
) -> list[dict[str, Any]]:
    """Find historically similar samples for a candidate.

    Args:
        candidate_features: Bucketed feature dict for the candidate
        all_samples: List of (code, date, bucketed_features, labels) tuples
        threshold: Minimum similarity score to include a match (default 0.5)
        max_matches: Maximum number of matches to return (default 100)

    Returns:
        List of match dicts sorted by similarity (descending), each with:
        {
            "code": str,
            "date": str,
            "similarity": float,
            "labels": dict,  # outcome labels from label_builder
        }
    """
    matches = []

    for code, date, sample_features, labels in all_samples:
        similarity = compute_similarity(candidate_features, sample_features)
        if similarity >= threshold:
            matches.append({
                "code": code,
                "date": date,
                "similarity": similarity,
                "labels": labels,
            })

    # Sort by similarity descending, then by date descending (prefer recent matches)
    matches.sort(key=lambda m: (m["similarity"], m["date"]), reverse=True)

    return matches[:max_matches]


def filter_by_coarse_buckets(
    candidate_features: dict[str, str | None],
    all_samples: list[tuple[str, str, dict[str, str | None], dict[str, Any]]],
    coarse_keys: list[str],
) -> list[tuple[str, str, dict[str, str | None], dict[str, Any]]]:
    """Coarse filtering: pre-filter samples by exact match on key features.

    This is a performance optimization to reduce the search space before
    computing full similarity.

    Args:
        candidate_features: Bucketed features for the candidate
        all_samples: Full sample pool
        coarse_keys: List of feature keys that must match exactly (e.g., ["pe_ttm", "return_5d"])

    Returns:
        Filtered list of samples where all coarse_keys match (within 1 bucket for quintiles)
    """
    filtered = []

    for code, date, sample_features, labels in all_samples:
        match = True
        for key in coarse_keys:
            cand_val = candidate_features.get(key)
            samp_val = sample_features.get(key)

            if cand_val is None or samp_val is None:
                # If either is missing, skip the coarse filter for this key
                continue

            if _is_quintile_value(cand_val) and _is_quintile_value(samp_val):
                cand_q = int(cand_val[1])
                samp_q = int(samp_val[1])
                if abs(cand_q - samp_q) > 1:
                    match = False
                    break
            else:
                if cand_val != samp_val:
                    match = False
                    break

        if match:
            filtered.append((code, date, sample_features, labels))

    return filtered


def assess_coverage_quality(match_count: int) -> str:
    """Assess the quality of historical coverage based on match count.

    Returns:
        "good" (≥20 matches), "sparse" (5-19 matches), or "insufficient" (<5 matches)
    """
    if match_count >= 20:
        return "good"
    elif match_count >= 5:
        return "sparse"
    else:
        return "insufficient"
