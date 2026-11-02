from paperman.downloaders.publisher import PUBLISHER_PATTERNS


def test_common_prefixes():
    """Verify all common DOI prefixes have patterns."""
    prefixes = [
        "10.1016",   # Elsevier
        "10.1038",   # Nature
        "10.1126",   # Science
        "10.1161",   # AHA Journals
        "10.1186",   # Springer/BioMed Central
        "10.1007",   # Springer
        "10.1093",   # Oxford
        "10.3390",   # MDPI
        "10.1111",   # Wiley
        "10.1021",   # ACS
        "10.1172",   # JCI
        "10.1073",   # PNAS
        "10.1371",   # PLOS
    ]
    for p in prefixes:
        assert p in PUBLISHER_PATTERNS, f"Missing pattern for {p}"


def test_pattern_format():
    """URL patterns contain template placeholders."""
    for doi_prefix, pattern in PUBLISHER_PATTERNS.items():
        assert "{doi}" in pattern or "{suffix}" in pattern, \
            f"Pattern for {doi_prefix} has no template vars: {pattern}"

from unittest.mock import patch
import requests
from paperman.downloaders.publisher import PublisherDownloader
from paperman.fetchers.crossref import CrossrefFetcher
from paperman.models.paper import Paper
from paperman.utils.network import HTTPClient

def test_elsevier_real_pii():
    paper = Paper(doi="10.1016/j.aca.2014.06.011",
                  landing_url="https://linkinghub.elsevier.com/retrieve/pii/S0003267014007247")
    assert PublisherDownloader().get_pdf_url(paper).endswith("/S0003267014007247/pdfft")

def test_rsc_registered_link():
    url = "https://pubs.rsc.org/en/content/articlepdf/2001/JM/B103299M"
    paper = Paper(doi="10.1039/b103299m", fulltext_links=[{"URL":url}])
    assert PublisherDownloader().get_pdf_url(paper) == url

def test_crossref_encodes_fragment():
    with patch("paperman.fetchers.crossref.http.get", return_value=None) as get:
        CrossrefFetcher()._fetch_by_doi("10.1002/test#")
        assert get.call_args.args[0].endswith("10.1002%2Ftest%23")

def test_landing_pdf_metadata():
    response = requests.Response()
    response.status_code = 200
    response.url = "https://pubs.rsc.org/article/123"
    response._content = b'<meta name="citation_pdf_url" content="/article-pdf/123">'
    with patch("paperman.downloaders.publisher.http.get", return_value=response):
        assert PublisherDownloader().get_pdf_url(Paper(doi="10.1039/test")) == "https://pubs.rsc.org/article-pdf/123"

def test_diagnostics_challenge_and_redaction(tmp_path, monkeypatch):
    import json
    target = tmp_path / "diagnostics.jsonl"
    monkeypatch.setenv("PAPERMAN_DIAGNOSTICS", str(target))
    response = requests.Response()
    response.status_code = 403
    response.url = "https://example.com/article?token=secret"
    response.headers["cf-mitigated"] = "challenge"
    response._content = b"<title>Just a moment...</title>"
    client = HTTPClient()
    with patch.object(client.sess, "get", return_value=response):
        assert client.get(response.url) is None
    row = json.loads(target.read_text())
    assert row["challenge"] and row["status"] == 403
    assert "secret" not in target.read_text()

def test_html_200_is_not_pdf(tmp_path):
    from paperman.downloaders.base import BaseDownloader
    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>preview</html>" * 1000
    with patch("paperman.downloaders.base.http.get", return_value=response):
        paper = Paper(doi="10.1039/test", pdf_url="https://example.com")
        assert PublisherDownloader().download(paper, tmp_path) is None
    assert not list(tmp_path.glob("*.pdf"))

def test_wiley_does_not_require_api_for_registered_pdf():
    paper = Paper(doi="10.1002/adfm.201907570", fulltext_links=[
        {"URL":"https://api.wiley.com/onlinelibrary/tdm/v1/articles/test",
         "content-type":"application/pdf"}])
    with patch("paperman.downloaders.publisher.http.head", return_value=None):
        assert PublisherDownloader().get_pdf_url(paper) == "https://onlinelibrary.wiley.com/doi/pdf/10.1002/adfm.201907570"

def test_rsc_http_link_upgraded():
    paper = Paper(doi="10.1039/test", fulltext_links=[
        {"URL":"http://pubs.rsc.org/en/content/articlepdf/2001/JM/test"}])
    assert PublisherDownloader().get_pdf_url(paper).startswith("https://")
