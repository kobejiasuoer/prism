# packages/screener/historical_edge/tests/test_sample_matcher.py
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages"))

from screener.historical_edge.sample_matcher import (
    assess_coverage_quality,
    compute_similarity,
    filter_by_coarse_buckets,
    match_similar_samples,
)


def test_compute_similarity_exact_match():
    """Test similarity computation for exact match."""
    candidate = {"pe_ttm": "Q2", "return_5d": "Q4", "is_st": "0.0"}
    sample = {"pe_ttm": "Q2", "return_5d": "Q4", "is_st": "0.0"}

    similarity = compute_similarity(candidate, sample)
    assert similarity == 1.0


def test_compute_similarity_within_one_bucket():
    """Test quintile within-1-bucket matching."""
    candidate = {"pe_ttm": "Q2", "return_5d": "Q4"}
    sample = {"pe_ttm": "Q3", "return_5d": "Q4"}  # pe_ttm off by 1 bucket

    similarity = compute_similarity(candidate, sample)
    # 2 features: pe_ttm matches (within 1), return_5d matches → 2/2 = 1.0
    assert similarity == 1.0


def test_compute_similarity_partial_match():
    """Test partial match (some features differ)."""
    candidate = {"pe_ttm": "Q2", "return_5d": "Q4", "roe": "Q3"}
    sample = {"pe_ttm": "Q2", "return_5d": "Q1", "roe": "Q3"}  # return_5d off by 3 buckets

    similarity = compute_similarity(candidate, sample)
    # 3 features: pe_ttm match, return_5d no match, roe match → 2/3 ≈ 0.67
    assert 0.6 < similarity < 0.7


def test_compute_similarity_no_overlap():
    """Test similarity when no common non-None features."""
    candidate = {"pe_ttm": "Q2", "return_5d": None}
    sample = {"roe": "Q3", "pb": "Q1"}

    similarity = compute_similarity(candidate, sample)
    assert similarity == 0.0


def test_match_similar_samples_filters_by_threshold():
    """Test sample matching with threshold filtering."""
    candidate = {"pe_ttm": "Q2", "return_5d": "Q4"}

    samples = [
        ("000001", "2023-01-05", {"pe_ttm": "Q2", "return_5d": "Q4"}, {"5d": {"label": "validated"}}),  # 1.0 similarity
        ("000002", "2023-01-05", {"pe_ttm": "Q3", "return_5d": "Q4"}, {"5d": {"label": "validated"}}),  # 1.0 (within 1)
        ("000003", "2023-01-05", {"pe_ttm": "Q5", "return_5d": "Q1"}, {"5d": {"label": "invalidated"}}),  # 0.0 (both off by >1)
    ]

    matches = match_similar_samples(candidate, samples, threshold=0.5, max_matches=100)

    assert len(matches) == 2  # First 2 samples match
    assert matches[0]["code"] in {"000001", "000002"}
    assert matches[0]["similarity"] == 1.0


def test_match_similar_samples_respects_max_matches():
    """Test max_matches limit."""
    candidate = {"pe_ttm": "Q2"}

    samples = [(f"00000{i}", "2023-01-05", {"pe_ttm": "Q2"}, {"5d": {}}) for i in range(150)]

    matches = match_similar_samples(candidate, samples, threshold=0.5, max_matches=100)

    assert len(matches) == 100


def test_filter_by_coarse_buckets():
    """Test coarse filtering on key features."""
    candidate = {"pe_ttm": "Q2", "return_5d": "Q4", "roe": "Q3"}

    samples = [
        ("000001", "2023-01-05", {"pe_ttm": "Q2", "return_5d": "Q4", "roe": "Q1"}, {}),  # pe_ttm+return_5d match
        ("000002", "2023-01-05", {"pe_ttm": "Q2", "return_5d": "Q1", "roe": "Q3"}, {}),  # pe_ttm match, return_5d no
        ("000003", "2023-01-05", {"pe_ttm": "Q5", "return_5d": "Q4", "roe": "Q3"}, {}),  # return_5d match, pe_ttm no
    ]

    filtered = filter_by_coarse_buckets(candidate, samples, coarse_keys=["pe_ttm", "return_5d"])

    # Only 000001 matches both coarse keys
    assert len(filtered) == 1
    assert filtered[0][0] == "000001"


def test_assess_coverage_quality():
    """Test coverage quality assessment."""
    assert assess_coverage_quality(25) == "good"
    assert assess_coverage_quality(20) == "good"
    assert assess_coverage_quality(19) == "sparse"
    assert assess_coverage_quality(5) == "sparse"
    assert assess_coverage_quality(4) == "insufficient"
    assert assess_coverage_quality(0) == "insufficient"
