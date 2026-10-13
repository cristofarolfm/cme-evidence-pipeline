"""Offline tests for the verifier (no network: check_pubmed=False)."""
from pipeline.verify import numbers, parse_cites, spelled_numbers, verify

SOURCES = {
    "PMID:111": "Phase 3 trial. Seven hundred eighteen patients were randomized. Hazard ratio 0.71; median PFS 13.1 months.",
    "NCT:NCT00000001": "Dostarlimab plus carboplatin-paclitaxel in endometrial cancer",
}


def status(md: str) -> list[str]:
    return [f.status for f in verify(md, SOURCES, check_pubmed=False)]


def test_parse_multiple_citations():
    assert parse_cites("x [PMID:111, PMID:222] y [NCT:NCT00000001]") == ["PMID:111", "PMID:222", "NCT:NCT00000001"]


def test_numbers_ignore_years_and_small_counts():
    assert numbers("In 2023, 3 trials found HR 0.71 and 45% response") == {"0.71", "45"}


def test_spelled_numbers():
    assert spelled_numbers("Seven hundred eighteen patients") == ["718"]


def test_supported_sentence_is_ok():
    assert status("## Evidence\nThe hazard ratio was 0.71 and median PFS 13.1 months in 718 randomized patients [PMID:111].") == ["OK"]


def test_wrong_number_is_flagged():
    assert status("## Evidence\nThe hazard ratio was 0.75 in randomized patients [PMID:111].") == ["NUMBER_NOT_IN_SOURCE"]


def test_unknown_citation_is_flagged():
    assert status("## Evidence\nThe hazard ratio was 0.71 [PMID:999].") == ["UNKNOWN_ID"]


def test_uncited_claim_is_flagged():
    assert status("## Evidence\nSurvival improved by 40% with immunotherapy.") == ["UNCITED"]


def test_unrelated_citation_is_weak():
    assert status("## Evidence\nHospital admissions for bowel obstruction decreased substantially [NCT:NCT00000001].") == ["WEAK_SUPPORT"]


def test_learning_objectives_need_no_citation():
    assert status("## Proposed learning objectives\n1. Compare survival outcomes across regimens.") == ["OK"]
