from unittest.mock import Mock
from paperman.downloaders.scihub import SciHubDownloader
from paperman.downloaders.pipeline import DownloadPipeline
from paperman.models.paper import Paper

def test_extract_all_pdf_elements():
    html='<embed src="/a.pdf"><object data="//cdn.example/b.pdf"></object><a href="c.pdf">save</a>'
    assert SciHubDownloader.extract_urls(html, "https://example/doi/x") == [
        "https://example/a.pdf", "https://cdn.example/b.pdf", "https://example/doi/c.pdf"]

def test_pipeline_tries_next_candidate(tmp_path):
    source=Mock()
    source.name="test"
    source.iter_pdf_urls.return_value=iter(["https://example/bad","https://example/good"])
    path=tmp_path/"good.pdf"
    source.download.side_effect=[None,path]
    pipeline=DownloadPipeline()
    pipeline.downloaders=[source]
    paper=Paper(doi="10.1002/test")
    assert pipeline.download(paper,tmp_path,retries=0)==path
    assert source.download.call_count==2

def test_proxy_isolated(monkeypatch):
    from paperman.utils.network import http
    original=dict(http.sess.proxies)
    monkeypatch.setenv("PAPERMAN_SCIHUB_PROXY","http://127.0.0.1:1234")
    source=SciHubDownloader()
    assert source.proxy=="http://127.0.0.1:1234"
    assert http.sess.proxies==original
