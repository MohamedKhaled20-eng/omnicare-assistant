from __future__ import annotations

from app.agent.graph import _ensure_citations, _select_sources

S1 = "sample_policy.md — Section 1: Home Water Damage Coverage"
S2 = "sample_policy.md — Section 2: Personal Property Protection"


def test_only_cited_sections_are_returned() -> None:
    answer = "Jewelry needs appraisals (Source: sample_policy.md — Section 2: Personal Property Protection)."
    assert _select_sources(answer, [S2, S1]) == [S2]


def test_short_section_reference_counts_as_citation() -> None:
    assert _select_sources("Per Section 1, pipe bursts are covered.", [S1, S2]) == [S1]


def test_uncited_answer_falls_back_to_best_hit_and_gets_a_citation_line() -> None:
    answer = "Pipe bursts are covered up to $25,000."
    sources = _select_sources(answer, [S1, S2])
    assert sources == [S1]
    assert _ensure_citations(answer, sources).endswith(f"Sources:\n- {S1}")


def test_decline_gets_no_sources() -> None:
    answer = "I couldn't find that in the policy documents. Please contact support."
    assert _select_sources(answer, [S1, S2]) == []


def test_no_retrieval_means_no_sources() -> None:
    assert _select_sources("Claim CLM-8821 is Approved.", []) == []


def test_citation_not_duplicated_when_already_present() -> None:
    answer = f"Covered. ({S1})"
    assert _ensure_citations(answer, [S1]) == answer
