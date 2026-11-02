from unittest.mock import Mock, patch
from paperman.models.paper import Paper
from paperman.fetchers.arxiv import ArxivFetcher
from paperman.downloaders.pipeline import DownloadPipeline

def feed(doi="", extra=""):
    return '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry><id>https://arxiv.org/abs/2401.12345v2</id><title>Polymer Test</title><author><name>A Smith</name></author><arxiv:doi>'+doi+'</arxiv:doi></entry>'+extra+'</feed>'

def lookup(xml):
    with patch("paperman.fetchers.arxiv.http.get", return_value=Mock(text=xml)):
        return ArxivFetcher().find_matching_preprint(Paper(doi="10.1/test",title="Polymer Test",authors=["Ann Smith"]))

def test_title_author_and_doi_rules():
    assert lookup(feed()).arxiv_id == "2401.12345v2"
    assert lookup(feed("10.1/test"))
    assert lookup(feed("10.1/different")) is None
    assert lookup(feed().replace("A Smith","A Jones")) is None
    assert lookup("<bad>") is None

def test_ambiguous_title_rejected():
    extra='<entry><id>https://arxiv.org/abs/2402.11111</id><title>Polymer Test</title><author><name>A Smith</name></author></entry>'
    assert lookup(feed(extra=extra)) is None

def test_order():
    assert [x.name for x in DownloadPipeline().downloaders] == ["arxiv","pmc","scihub","publisher"]

def test_title_fallback_after_both_rounds(tmp_path):
    class Fail:
        name="publisher"
        calls=0
        def get_pdf_url(self,paper):
            self.calls+=1
            return None
    failure=Fail();pipeline=DownloadPipeline();pipeline.downloaders=[failure]
    original=Paper(doi="10.1/test",title="Polymer Test")
    candidate=Paper(arxiv_id="2401.12345v2",title="Polymer Test")
    path=tmp_path/"paper.pdf"
    def lookup(paper):
        assert failure.calls==2
        return candidate
    with patch("paperman.downloaders.pipeline.time.sleep"), patch.object(ArxivFetcher,"find_matching_preprint",side_effect=lookup), patch("paperman.downloaders.pipeline.ArxivDownloader.download",return_value=path):
        assert pipeline.download(original,tmp_path)==path
    assert original.doi=="10.1/test" and original.pdf_source=="arxiv_title"
    assert original.arxiv_id=="2401.12345v2"

def test_early_success_does_not_search(tmp_path):
    source=Mock(name="success");source.name="pmc";source.iter_pdf_urls.return_value=iter(["https://example/test.pdf"]);source.download.return_value=tmp_path/"ok.pdf"
    pipeline=DownloadPipeline();pipeline.downloaders=[source]
    with patch.object(ArxivFetcher,"find_matching_preprint") as search:
        assert pipeline.download(Paper(doi="10.1/test"),tmp_path)
        search.assert_not_called()
