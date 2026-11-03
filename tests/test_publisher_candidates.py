"""Publisher candidate traversal and unknown-platform regression tests."""
from unittest.mock import patch

import pytest
import requests

from paperman.downloaders.pipeline import DownloadPipeline
from paperman.downloaders.publisher import PublisherDownloader
from paperman.models.paper import Paper


def response(url, body):
    r = requests.Response()
    r.status_code = 200
    r.url = url
    r._content = body.encode() if isinstance(body, str) else body
    return r


def test_pipeline_tries_next_pdf_without_eager_landing_fetch(tmp_path):
    paper = Paper(doi="10.9999/example", fulltext_links=[
        {"URL": "https://example.org/first.pdf"},
        {"URL": "https://example.org/second.pdf"},
    ])
    good = response("https://example.org/second.pdf", b"%PDF-1.4\n" + b"x" * 11000)
    # An HTML login page on the first URL must not end publisher traversal.
    bad = response("https://example.org/first.pdf", "<html>login</html>")
    with patch("paperman.utils.network.http.get", side_effect=[bad, good]) as get:
        result = DownloadPipeline(["publisher"]).download(paper, tmp_path, retries=0)
    assert result and result.read_bytes() == good.content
    assert get.call_count == 2
    assert paper.pdf_source == "publisher"
    assert paper.pdf_url.endswith("second.pdf")


@pytest.mark.parametrize("doi", ["10.1115/1.4067407", "10.9999/unknown"])
def test_unknown_prefix_uses_page_metadata(doi):
    landing = "https://example.org/journal/article/123"
    page = response(landing, '<meta name="citation_doi" content="' + doi + '">'
                    '<meta name="citation_pdf_url" content="/journal/article-pdf/123/main.pdf">')
    with patch("paperman.utils.network.http.get", return_value=page):
        assert PublisherDownloader().get_pdf_url(Paper(doi=doi, landing_url=landing)) == (
            "https://example.org/journal/article-pdf/123/main.pdf")


def test_dedup_unsafe_and_supplementary_links():
    landing = "https://example.org/article"
    page = response(landing, """
        <meta name="citation_pdf_url" content="/main.pdf#page=1">
        <link type="application/pdf" href="/main.pdf">
        <a href="/supplement.pdf">Supporting information</a>
        <div class="references"><a href="/other.pdf">PDF</a></div>
        <a href="/alternate.pdf">Download article PDF</a>
        <meta name="citation_pdf_url" content="javascript:alert(1)">
        <meta name="citation_pdf_url" content="https://user:pass@example.org/private.pdf">
    """)
    with patch("paperman.utils.network.http.get", return_value=page):
        urls = list(PublisherDownloader().iter_pdf_urls(Paper(doi="10.9999/test", landing_url=landing)))
    assert urls == ["https://example.org/main.pdf", "https://example.org/alternate.pdf"]


def test_landing_with_different_doi_is_rejected():
    page = response("https://example.org/article",
                    '<meta name="citation_doi" content="10.9999/different">'
                    '<meta name="citation_pdf_url" content="/wrong.pdf">')
    with patch("paperman.utils.network.http.get", return_value=page):
        assert list(PublisherDownloader().iter_pdf_urls(Paper(doi="10.9999/test"))) == []


def test_template_failure_reaches_landing(tmp_path):
    paper = Paper(doi="10.1002/example", landing_url="https://example.org/article")
    page = response(paper.landing_url, '<meta name="citation_pdf_url" content="/real.pdf">')
    good = response("https://example.org/real.pdf", b"%PDF-1.4\n" + b"x" * 11000)
    def get(url, **kwargs):
        if "/doi/pdf/" in url:
            return None
        if url == paper.landing_url:
            return page
        if url == good.url:
            return good
        raise AssertionError(url)
    with patch("paperman.utils.network.http.get", side_effect=get), patch("paperman.utils.network.http.head") as head:
        assert DownloadPipeline(["publisher"]).download(paper, tmp_path, retries=0)
        head.assert_not_called()


def test_elsevier_without_pii_never_guesses_doi_suffix():
    page = response("https://example.org/article", "<html>No PDF</html>")
    with patch("paperman.utils.network.http.get", return_value=page):
        assert list(PublisherDownloader().iter_pdf_urls(Paper(doi="10.1016/j.fake.2024.123"))) == []


def test_broken_landing_tries_doi_resolver():
    page = response("https://new.example.org/article", '<link type="application/pdf" href="/main.pdf">')
    with patch("paperman.utils.network.http.get", side_effect=[None, page]) as get:
        assert PublisherDownloader().get_pdf_url(Paper(doi="10.9999/test", landing_url="https://old.example.org/x")) == "https://new.example.org/main.pdf"
    assert get.call_count == 2


def test_exact_prefix_not_partial_match():
    with patch("paperman.utils.network.http.get", return_value=None):
        assert PublisherDownloader().get_pdf_url(Paper(doi="10.10020/test")) is None


def test_candidate_cap_and_laziness():
    paper = Paper(doi="10.9999/test", fulltext_links=[
        {"URL": f"https://example.org/{i}.pdf"} for i in range(30)])
    with patch("paperman.utils.network.http.get") as get:
        assert len(list(PublisherDownloader().iter_pdf_urls(paper))) == 12
        get.assert_not_called()
