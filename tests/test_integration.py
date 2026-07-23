"""Integration tests for the download pipeline (no network required)."""

from pathlib import Path

from paperman.downloaders.pipeline import DownloadPipeline
from paperman.downloaders.publisher import PUBLISHER_PATTERNS
from paperman.models.paper import Paper, SourceType


def make_paper(doi="10.1186/s13054-026-05843-y", title="Test"):
    return Paper(
        source_type=SourceType.doi,
        source_id=doi,
        doi=doi,
        title=title,
        authors=["Test Author"],
        journal="Test Journal",
        year=2026,
    )


def test_publisher_patterns_all_have_templates():
    """Every publisher pattern has valid template variables."""
    for prefix, pattern in PUBLISHER_PATTERNS.items():
        assert "{doi}" in pattern or "{suffix}" in pattern, f"{prefix}: {pattern}"


def test_publisher_url_construction():
    """Verify publisher URL construction for common prefixes."""
    from paperman.downloaders.publisher import PublisherDownloader
    dl = PublisherDownloader()

    cases = [
        ("10.1038/s41586-026-10644-y", "nature.com/articles/s41586-026-10644-y.pdf"),
        ("10.1126/science.aef0825", "science.org/doi/pdf/10.1126/science.aef0825"),
        ("10.1186/s13054-026-05843-y", "link.springer.com/content/pdf/10.1186/s13054-026-05843-y.pdf"),
        ("10.3390/jcm15134884", "mdpi.com/10.3390/jcm15134884/pdf"),
        ("10.1073/pnas.2407765121", "pnas.org/doi/pdf/10.1073/pnas.2407765121"),
        ("10.1172/jci129277", "jci.org/articles/view/jci129277/pdf"),
    ]

    for doi, expected_segment in cases:
        paper = make_paper(doi=doi)
        url = dl.get_pdf_url(paper)
        assert url is not None, f"No URL for {doi}"
        assert expected_segment in url, f"{doi}: expected {expected_segment} in {url}"


def test_doi_prefix_match_longest_first():
    """10.1016/xxx should match Elsevier, not mis-match to a generic 10.10xx."""
    from paperman.downloaders.publisher import PublisherDownloader
    dl = PublisherDownloader()
    paper = make_paper(doi="10.1016/j.cell.2024.04.023")
    url = dl.get_pdf_url(paper)
    assert url is not None
    assert "sciencedirect" in url


def test_publisher_pattern_count():
    """Should have at least 25 publisher patterns."""
    assert len(PUBLISHER_PATTERNS) >= 25, f"Only {len(PUBLISHER_PATTERNS)} patterns"


def test_publisher_doi_prefixes_unique():
    """No duplicate or overlapping prefixes."""
    prefixes = sorted(PUBLISHER_PATTERNS.keys(), key=len, reverse=True)
    for i, p in enumerate(prefixes):
        for q in prefixes[i + 1:]:
            assert not q.startswith(p), f"{p} overlaps with {q}"


def test_new_prefixes_added():
    """Verify newly added patterns exist."""
    for prefix in ("10.1056", "10.1136", "10.1152", "10.1158", "10.1681"):
        assert prefix in PUBLISHER_PATTERNS, f"Missing: {prefix}"


def test_pipeline_downloaders_sorted():
    """Downloaders should be in priority order."""
    pipeline = DownloadPipeline()
    priorities = [d.priority for d in pipeline.downloaders]
    assert priorities == sorted(priorities)
    assert pipeline.downloaders[0].name == "arxiv"
    assert pipeline.downloaders[-1].name == "scihub"
