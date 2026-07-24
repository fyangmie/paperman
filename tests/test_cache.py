from pathlib import Path

from paperman.models.paper import Paper, SourceType
from paperman.cache import PaperCache


def make_paper(doi="10.1234/test.5678", pmid="12345678", title="Test Paper"):
    return Paper(
        source_type=SourceType.doi,
        source_id=doi,
        doi=doi,
        pmid=pmid,
        pmcid="PMC12345678",
        title=title,
        authors=["Smith, J"],
        journal="Test Journal",
        year=2024,
    )


def test_cache_set_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = make_paper()
    cache.set(p)
    retrieved = cache.get("10.1234/test.5678")
    assert retrieved is not None
    assert retrieved.doi == "10.1234/test.5678"
    assert retrieved.title == "Test Paper"
    cache.close()


def test_cache_get_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    assert cache.get("10.9999/nonexistent") is None
    cache.close()


def test_cache_get_by_pmid(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = make_paper()
    cache.set(p)
    retrieved = cache.get_by_pmid("12345678")
    assert retrieved is not None
    assert retrieved.pmid == "12345678"
    cache.close()


def test_cache_get_by_pmid_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    assert cache.get_by_pmid("99999999") is None
    cache.close()


def test_cache_set_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p1 = make_paper(title="First Version")
    cache.set(p1)
    p2 = make_paper(title="Second Version")
    cache.set(p2)
    retrieved = cache.get("10.1234/test.5678")
    assert retrieved.title == "Second Version"
    cache.close()


def test_cache_set_skips_empty_doi(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = Paper(source_type=SourceType.title, source_id="a title", title="No DOI")
    cache.set(p)  # should not raise
    assert cache.list_all() == []
    cache.close()


def test_cache_list_all(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p1 = make_paper(doi="10.1111/a", pmid="11111111", title="Paper A")
    p2 = make_paper(doi="10.2222/b", pmid="22222222", title="Paper B")
    cache.set(p1)
    cache.set(p2)
    all_papers = cache.list_all()
    assert len(all_papers) == 2
    titles = {p.title for p in all_papers}
    assert titles == {"Paper A", "Paper B"}
    cache.close()


def test_cache_search_by_title(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.set(make_paper(title="Machine Learning in Biology"))
    cache.set(make_paper(doi="10.2222/b", pmid="22222222", title="Deep Learning"))
    results = cache.search("biology")
    assert len(results) == 1
    assert "Biology" in results[0].title
    cache.close()


def test_cache_search_by_author(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.set(make_paper())
    results = cache.search("Smith")
    assert len(results) == 1
    cache.close()


def test_cache_search_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.set(make_paper())
    results = cache.search("xyznonexistent")
    assert results == []
    cache.close()


def test_cache_search_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.set(make_paper(title="Nature Genetics"))
    assert len(cache.search("nature")) == 1
    assert len(cache.search("NATURE")) == 1
    assert len(cache.search("Genetics")) == 1
    cache.close()


def test_cache_search_by_journal(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.set(make_paper(title="Paper A"))
    cache.set(make_paper(doi="10.2222/b", pmid="22222222", title="Paper B"))
    results = cache.search("test journal")
    assert len(results) == 2
    cache.close()


def test_cache_update_pdf_path(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = make_paper()
    cache.set(p)
    pdf_path = tmp_path / "paper.pdf"
    cache.update_pdf_path("10.1234/test.5678", pdf_path)
    retrieved = cache.get("10.1234/test.5678")
    assert retrieved.pdf_path == pdf_path
    cache.close()


def test_cache_remove(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    p = make_paper()
    cache.set(p)
    cache.remove("10.1234/test.5678")
    assert cache.get("10.1234/test.5678") is None
    assert len(cache.list_all()) == 0
    cache.close()


def test_cache_remove_nonexistent(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.remove("10.9999/nonexistent")
    cache.close()


def test_cache_context_manager(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    with PaperCache() as cache:
        cache.set(make_paper())
        assert cache.get("10.1234/test.5678") is not None


def test_cache_usable_after_create(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.cache.CACHE_DIR", tmp_path)
    cache = PaperCache()
    cache.close()
