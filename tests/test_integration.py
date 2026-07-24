"""Integration tests for the download pipeline (no network required)."""

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


def test_openalex_abstract_decoding():
    """OpenAlex inverted index abstract is decoded correctly."""
    from paperman.fetchers.openalex import OpenAlexFetcher
    inverted = {"hello": [0, 3], "world": [1], "test": [2]}
    result = OpenAlexFetcher._decode_abstract(inverted)
    assert result == "hello world test hello"


def test_openalex_abstract_empty():
    from paperman.fetchers.openalex import OpenAlexFetcher
    assert OpenAlexFetcher._decode_abstract({}) == ""


def test_openalex_parse_minimal():
    """OpenAlex _parse handles minimal response with just DOI."""
    from paperman.fetchers.openalex import OpenAlexFetcher
    data = {"doi": "https://doi.org/10.1234/test"}
    paper = OpenAlexFetcher._parse(data)
    assert paper is not None
    assert paper.doi == "10.1234/test"
    assert paper.title == ""


def test_import_bibtex_parse(tmp_path):
    """BibTeX file is parsed and entries extracted correctly."""
    from paperman.cli import classify
    bib = """@article{key1,
  author = {Smith, J},
  title = {Import Test Paper},
  journal = {Test Journal},
  year = {2024},
  doi = {10.1234/import.test},
}
"""
    bib_path = tmp_path / "test.bib"
    bib_path.write_text(bib)
    import bibtexparser
    with open(bib_path) as f:
        db = bibtexparser.load(f)
    assert len(db.entries) == 1
    entry = db.entries[0]
    assert entry["doi"] == "10.1234/import.test"
    assert entry["title"] == "Import Test Paper"
    src = classify(entry["doi"])
    assert src.type.value == "doi"


def test_import_bibtex_missing_doi(tmp_path):
    """BibTeX entry with no DOI/PMID but with title can still be classified."""
    from paperman.cli import classify
    bib = """@article{key2,
  author = {Doe, J},
  title = {A Paper Without DOI},
  journal = {Unknown Journal},
  year = {2023},
}
"""
    bib_path = tmp_path / "test2.bib"
    bib_path.write_text(bib)
    import bibtexparser
    with open(bib_path) as f:
        db = bibtexparser.load(f)
    entry = db.entries[0]
    src = classify(entry["title"])
    assert src.type.value == "title"


def test_open_command_cache_lookup(tmp_path, monkeypatch):
    """open command looks up paper in cache."""
    from paperman.cache import PaperCache
    from paperman.models.paper import Paper, SourceType
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = Paper(
        source_type=SourceType.doi, source_id="10.1234/open.test", doi="10.1234/open.test",
        title="Open Test", pdf_path=tmp_path / "exists.pdf",
    )
    tmp_path.joinpath("exists.pdf").write_text("dummy pdf")
    cache.set(p)
    retrieved = cache.get("10.1234/open.test")
    assert retrieved is not None
    assert retrieved.pdf_path is not None
    assert retrieved.pdf_path.exists()
    cache.close()


def test_biorxiv_no_version():
    """bioRxiv pattern no longer includes v1."""
    from paperman.downloaders.publisher import PublisherDownloader
    dl = PublisherDownloader()
    paper = make_paper(doi="10.1101/2023.01.01.123456")
    url = dl.get_pdf_url(paper)
    assert url is not None
    assert "v1" not in url, f"Unexpected v1 in URL: {url}"
    assert url == "https://www.biorxiv.org/content/10.1101/2023.01.01.123456.full.pdf"


def test_plos_journal_extraction():
    """PLOS pattern now extracts journal slug from DOI."""
    from paperman.downloaders.publisher import PublisherDownloader
    dl = PublisherDownloader()
    cases = [
        ("10.1371/journal.pbio.3003003", "journals.plos.org/plosbiology"),
        ("10.1371/journal.pgen.1012345", "journals.plos.org/plosgenetics"),
        ("10.1371/journal.pone.0123456", "journals.plos.org/plosone"),
        ("10.1371/journal.pmed.0456789", "journals.plos.org/plosmedicine"),
        ("10.1371/journal.pntd.0012345", "journals.plos.org/plosntds"),
    ]
    for doi, expected in cases:
        paper = make_paper(doi=doi)
        url = dl.get_pdf_url(paper)
        assert url is not None, f"No URL for {doi}"
        assert expected in url, f"{doi}: expected {expected} in {url}"
