"""Unit tests for all fetchers with mocked HTTP responses."""

from unittest.mock import patch

from paperman.models.paper import SourceType


class MockResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json = json_data or {}
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json


# ── Crossref ──────────────────────────────────────────────────────────────

CROSSREF_DOI_RESP = {
    "message": {
        "DOI": "10.1234/test.5678",
        "title": ["Test Crossref Paper"],
        "author": [{"given": "John", "family": "Smith"}],
        "container-title": ["Journal of Testing"],
        "published-print": {"date-parts": [[2024]]},
        "volume": "10",
        "issue": "2",
        "page": "100-110",
        "publisher": "Test Publisher",
    }
}

CROSSREF_SEARCH_RESP = {
    "message": {
        "items": [CROSSREF_DOI_RESP["message"]],
    }
}


def test_crossref_fetch_by_doi():
    from paperman.fetchers.crossref import CrossrefFetcher
    with patch("paperman.fetchers.crossref.http.get", return_value=MockResponse(CROSSREF_DOI_RESP)):
        paper = CrossrefFetcher().fetch("10.1234/test.5678", SourceType.doi)
    assert paper is not None
    assert paper.doi == "10.1234/test.5678"
    assert paper.title == "Test Crossref Paper"
    assert paper.year == 2024
    assert paper.journal == "Journal of Testing"


def test_crossref_fetch_by_doi_not_found():
    from paperman.fetchers.crossref import CrossrefFetcher
    with patch("paperman.fetchers.crossref.http.get", return_value=None):
        paper = CrossrefFetcher().fetch("10.9999/nonexistent", SourceType.doi)
    assert paper is None


def test_crossref_fetch_by_title():
    from paperman.fetchers.crossref import CrossrefFetcher
    with patch("paperman.fetchers.crossref.http.get", return_value=MockResponse(CROSSREF_SEARCH_RESP)):
        paper = CrossrefFetcher().fetch("test paper", SourceType.title)
    assert paper is not None
    assert paper.doi == "10.1234/test.5678"


def test_crossref_fetch_by_title_not_found():
    from paperman.fetchers.crossref import CrossrefFetcher
    with patch("paperman.fetchers.crossref.http.get", return_value=MockResponse({"message": {"items": []}})):
        paper = CrossrefFetcher().fetch("nonexistent", SourceType.title)
    assert paper is None


def test_crossref_unsupported_type():
    from paperman.fetchers.crossref import CrossrefFetcher
    assert CrossrefFetcher().fetch("12345678", SourceType.pmid) is None


def test_crossref_parse():
    from paperman.fetchers.crossref import CrossrefFetcher
    paper = CrossrefFetcher._parse(CROSSREF_DOI_RESP["message"])
    assert paper is not None
    assert "John" in paper.authors[0]


# ── OpenAlex ──────────────────────────────────────────────────────────────

OPENALEX_DOI_RESP = {
    "doi": "https://doi.org/10.1234/test.5678",
    "title": "Test OpenAlex Paper",
    "publication_year": 2024,
    "authorships": [
        {"author": {"display_name": "Jane Doe"}},
    ],
    "primary_location": {
        "source": {"display_name": "Open Journal", "publisher": "Open Pub"},
    },
    "biblio": {"volume": "10", "issue": "2", "pages": "100-110"},
    "concepts": [
        {"display_name": "Machine Learning", "score": 0.95},
        {"display_name": "Deep Learning", "score": 0.25},
    ],
    "open_access": {"is_oa": True, "oa_url": "https://open.example.com/paper.pdf"},
    "abstract_inverted_index": {"This": [0], "is": [1], "an": [2], "abstract": [3]},
}

OPENALEX_SEARCH_RESP = {
    "results": [OPENALEX_DOI_RESP],
}


def test_openalex_fetch_by_doi():
    from paperman.fetchers.openalex import OpenAlexFetcher
    with patch("paperman.fetchers.openalex.http.get", return_value=MockResponse(OPENALEX_DOI_RESP)):
        paper = OpenAlexFetcher().fetch("10.1234/test.5678", SourceType.doi)
    assert paper is not None
    assert paper.doi == "10.1234/test.5678"
    assert paper.title == "Test OpenAlex Paper"
    assert paper.year == 2024
    assert len(paper.authors) == 1
    assert paper.keywords == ["Machine Learning"]
    assert paper.pdf_url == "https://open.example.com/paper.pdf"
    assert "abstract" in paper.abstract.lower()


def test_openalex_fetch_by_doi_not_found():
    from paperman.fetchers.openalex import OpenAlexFetcher
    with patch("paperman.fetchers.openalex.http.get", return_value=None):
        paper = OpenAlexFetcher().fetch("10.9999/nonexistent", SourceType.doi)
    assert paper is None


def test_openalex_fetch_by_title():
    from paperman.fetchers.openalex import OpenAlexFetcher
    with patch("paperman.fetchers.openalex.http.get", return_value=MockResponse(OPENALEX_SEARCH_RESP)):
        paper = OpenAlexFetcher().fetch("test paper", SourceType.title)
    assert paper is not None
    assert paper.title == "Test OpenAlex Paper"


def test_openalex_search_by_query():
    from paperman.fetchers.openalex import OpenAlexFetcher
    with patch("paperman.fetchers.openalex.http.get", return_value=MockResponse(OPENALEX_SEARCH_RESP)):
        papers = OpenAlexFetcher.search_by_query("test", limit=5)
    assert len(papers) == 1


def test_openalex_search_no_results():
    from paperman.fetchers.openalex import OpenAlexFetcher
    with patch("paperman.fetchers.openalex.http.get", return_value=MockResponse({"results": []})):
        papers = OpenAlexFetcher.search_by_query("nonexistent", limit=5)
    assert papers == []


def test_openalex_unsupported_type():
    from paperman.fetchers.openalex import OpenAlexFetcher
    assert OpenAlexFetcher().fetch("12345678", SourceType.pmid) is None


# ── PubMed ────────────────────────────────────────────────────────────────

PUEMD_SUMMARY_RESP = {
    "result": {
        "12345678": {
            "uid": "12345678",
            "title": "Test PubMed Paper",
            "source": "Journal of Medicine",
            "pubdate": "2024 Jan",
            "authors": [{"name": "Alice Brown"}],
            "elocationid": "doi: 10.1234/pubmed.test",
        }
    }
}

PUBMED_ESEARCH_RESP = {
    "esearchresult": {"idlist": ["12345678"]},
}

PUBMED_IDCONV_RESP = {
    "records": [{"pmcid": "PMC12345678"}],
}

EUROPEPMC_RESP = {
    "resultList": {
        "result": [
            {
                "doi": "10.1234/europe.test",
                "pmcid": "PMC87654321",
                "pmid": "87654321",
                "title": "Test EuropePMC Paper",
                "authorString": "Charlie, D, Eve, F",
                "journalTitle": "European Journal",
                "firstPublicationDate": "2024-06-15",
            }
        ]
    }
}


def test_pubmed_fetch_by_pmid(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=MockResponse(PUEMD_SUMMARY_RESP)):
        paper = PubMedFetcher().fetch("12345678", SourceType.pmid)
    assert paper is not None
    assert paper.pmid == "12345678"
    assert paper.title == "Test PubMed Paper"
    assert paper.journal == "Journal of Medicine"
    assert paper.year == 2024


def test_pubmed_fetch_by_pmid_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=None):
        paper = PubMedFetcher().fetch("99999999", SourceType.pmid)
    assert paper is None


def test_pubmed_by_doi_returns_none():
    from paperman.fetchers.pubmed import PubMedFetcher
    assert PubMedFetcher().fetch("10.1234/test", SourceType.doi) is None


def test_pubmed_search_by_query(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    search_resp = MockResponse(PUBMED_ESEARCH_RESP)
    summary_resp = MockResponse(PUEMD_SUMMARY_RESP)
    with patch("paperman.fetchers.pubmed.http.get", side_effect=[search_resp, summary_resp]):
        papers = PubMedFetcher.search_by_query("cancer", limit=5)
    assert len(papers) == 1
    assert papers[0].pmid == "12345678"


def test_pubmed_search_no_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=MockResponse({"esearchresult": {"idlist": []}})):
        papers = PubMedFetcher.search_by_query("nonexistent", limit=5)
    assert papers == []


def test_pubmed_search_by_query_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=None):
        papers = PubMedFetcher.search_by_query("error", limit=5)
    assert papers == []


def test_pubmed_resolve_pmcid(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=MockResponse(PUBMED_IDCONV_RESP)):
        pmcid = PubMedFetcher.resolve_pmcid("10.1234/test")
    assert pmcid == "PMC12345678"


def test_pubmed_resolve_pmcid_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=MockResponse({"records": []})):
        pmcid = PubMedFetcher.resolve_pmcid("10.9999/nonexistent")
    assert pmcid is None


def test_pubmed_search_europepmc(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    with patch("paperman.fetchers.pubmed.http.get", return_value=MockResponse(EUROPEPMC_RESP)):
        papers = PubMedFetcher.search_europepmc("test", limit=5)
    assert len(papers) == 1
    assert papers[0].pmid == "87654321"
    assert papers[0].doi == "10.1234/europe.test"


def test_pubmed_extract_year():
    from paperman.fetchers.pubmed import PubMedFetcher
    assert PubMedFetcher._extract_year("2024 Jan") == 2024
    assert PubMedFetcher._extract_year("") is None
    assert PubMedFetcher._extract_year("no year") is None


def test_pubmed_clean_doi():
    from paperman.fetchers.pubmed import PubMedFetcher
    assert PubMedFetcher._clean_doi("doi: 10.1234/test.5678") == "10.1234/test.5678"
    assert PubMedFetcher._clean_doi("") == ""


# ── arXiv ─────────────────────────────────────────────────────────────────

ARXIV_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2505.13400v1</id>
    <title>Test ArXiv Paper</title>
    <summary>This is a test abstract.</summary>
    <author><name>John Arxiv</name></author>
    <link href="https://doi.org/10.1234/arxiv.test" title="doi"/>
    <link href="http://arxiv.org/pdf/2505.13400.pdf" title="pdf"/>
  </entry>
</feed>"""

ARXIV_EMPTY_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""


def test_arxiv_fetch_by_id():
    from paperman.fetchers.arxiv import ArxivFetcher
    with patch("paperman.fetchers.arxiv.http.get", return_value=MockResponse(text=ARXIV_XML)):
        paper = ArxivFetcher().fetch("2505.13400", SourceType.arxiv)
    assert paper is not None
    assert paper.arxiv_id == "2505.13400"
    assert "Test ArXiv Paper" in paper.title
    assert "test abstract" in paper.abstract
    assert paper.doi == "10.1234/arxiv.test"


def test_arxiv_fetch_not_found():
    from paperman.fetchers.arxiv import ArxivFetcher
    with patch("paperman.fetchers.arxiv.http.get", return_value=None):
        paper = ArxivFetcher().fetch("9999.99999", SourceType.arxiv)
    assert paper is None


def test_arxiv_fetch_empty_response():
    from paperman.fetchers.arxiv import ArxivFetcher
    with patch("paperman.fetchers.arxiv.http.get", return_value=MockResponse(text=ARXIV_EMPTY_XML)):
        paper = ArxivFetcher().fetch("9999.99999", SourceType.arxiv)
    assert paper is None


def test_arxiv_search_by_title():
    from paperman.fetchers.arxiv import ArxivFetcher
    with patch("paperman.fetchers.arxiv.http.get", return_value=MockResponse(text=ARXIV_XML)):
        paper = ArxivFetcher().fetch("test paper", SourceType.title)
    assert paper is not None
    assert "2505.13400" in paper.arxiv_id


def test_arxiv_unsupported_type():
    from paperman.fetchers.arxiv import ArxivFetcher
    assert ArxivFetcher().fetch("12345678", SourceType.pmid) is None


# ── PubMed Special Helpers ────────────────────────────────────────────────


def test_pubmed_ncbi_params_reads_key(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "config.ini")
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nncbi_api_key = mytestkey\n")
    from paperman.fetchers.pubmed import PubMedFetcher
    params = PubMedFetcher._ncbi_params(db="pubmed", id="12345", retmode="json")
    assert params["api_key"] == "mytestkey"
    assert params["db"] == "pubmed"


def test_pubmed_ncbi_params_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.fetchers.pubmed.CONFIG_PATH", tmp_path / "nonexistent.ini")
    from paperman.fetchers.pubmed import PubMedFetcher
    params = PubMedFetcher._ncbi_params(db="pubmed", id="12345")
    assert "api_key" not in params


def test_pubmed_clean_doi_complex():
    from paperman.fetchers.pubmed import PubMedFetcher
    assert PubMedFetcher._clean_doi("pii: S12345. 10.1234/complex.test.6789") == "10.1234/complex.test.6789"
