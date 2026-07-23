from paperman.models.paper import Paper, SourceType


def make_paper(**kwargs):
    defaults = dict(
        source_type=SourceType.doi,
        source_id="10.1234/test.5678",
        doi="10.1234/test.5678",
        title="Test Paper Title for Testing Purposes",
        authors=["Smith, J", "Doe, J", "Lee, K"],
        journal="Journal of Testing",
        year=2024,
        volume="10",
        issue="2",
        pages="100-110",
        pmid="12345678",
        pmcid="PMC12345678",
        publisher="Test Publisher",
    )
    defaults.update(kwargs)
    return Paper(**defaults)


def test_safe_filename():
    p = make_paper()
    name = p.safe_filename()
    assert "Test Paper Title for Testing Purposes" == name


def test_safe_filename_special_chars():
    p = make_paper(title="Paper: Test / with * special? chars")
    name = p.safe_filename()
    assert "/" not in name
    assert "*" not in name


def test_bibtex_basic():
    p = make_paper()
    bib = p.bibtex()
    assert bib.startswith("@article{")
    assert "Smith" in bib
    assert "10.1234/test.5678" in bib
    assert bib.strip().endswith("}")
    assert "pmid = {12345678}" in bib


def test_bibtex_escaping():
    p = make_paper(title="Test {Title} with & ampersand")
    bib = p.bibtex()
    assert "\\{" in bib
    assert "\\&" in bib


def test_to_yaml():
    p = make_paper()
    yaml = p.to_yaml()
    assert "title:" in yaml
    assert "doi:" in yaml
    assert "pmid:" in yaml
    assert "pmcid:" in yaml


def test_paper_defaults():
    p = Paper(source_type=SourceType.doi, source_id="test")
    assert p.title == ""
    assert p.authors == []
    assert p.year is None
    assert p.safe_filename() != ""
