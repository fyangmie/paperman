from pathlib import Path

from paperman.models.paper import Paper, SourceType
from paperman.exporters import save_yaml, save_bibtex, export_zotero


def make_paper(with_pdf=False):
    p = Paper(
        source_type=SourceType.doi,
        source_id="10.1234/test.5678",
        doi="10.1234/test.5678",
        title="Test Export Paper",
        authors=["Smith, J", "Doe, A"],
        journal="Journal of Testing",
        year=2024,
        volume="10",
        issue="2",
        pages="100-110",
        pmid="12345678",
        pmcid="PMC12345678",
        metadata_source="crossref",
        pdf_source="arxiv",
    )
    if with_pdf:
        p.pdf_path = Path("/tmp/test.pdf")
    return p


def test_save_yaml_creates_file(tmp_path):
    p = make_paper()
    path = save_yaml(p, tmp_path)
    assert path.exists()
    assert path.suffix == ".yaml"
    content = path.read_text()
    assert "Test Export Paper" in content
    assert "doi:" in content


def test_save_yaml_content(tmp_path):
    p = make_paper()
    path = save_yaml(p, tmp_path)
    content = path.read_text()
    assert "Smith, J" in content
    assert "Journal of Testing" in content
    assert "2024" in content


def test_save_bibtex_creates_file(tmp_path):
    p = make_paper()
    path = save_bibtex(p, tmp_path)
    assert path.exists()
    assert path.suffix == ".bib"
    content = path.read_text()
    assert content.startswith("@article{")


def test_save_bibtex_content(tmp_path):
    p = make_paper()
    path = save_bibtex(p, tmp_path)
    content = path.read_text()
    assert "Smith" in content
    assert "10.1234/test.5678" in content
    assert "pmid = {12345678}" in content
    assert content.strip().endswith("}")


def test_export_zotero_creates_bib(tmp_path):
    p = make_paper(with_pdf=True)
    paths = export_zotero(p, tmp_path)
    assert len(paths) == 1
    assert paths[0].suffix == ".bib"
    content = paths[0].read_text()
    assert "file = {" in content


def test_export_zotero_no_pdf_no_file_field(tmp_path):
    p = make_paper(with_pdf=False)
    paths = export_zotero(p, tmp_path)
    content = paths[0].read_text()
    assert "file = {" not in content


def test_export_zotero_pmcid_included(tmp_path):
    p = make_paper(with_pdf=True)
    paths = export_zotero(p, tmp_path)
    content = paths[0].read_text()
    assert "pmcid = {PMC12345678}" in content


def test_export_zotero_url_fallback(tmp_path):
    p = make_paper(with_pdf=False)
    p.pdf_url = "https://arxiv.org/pdf/1234.5678.pdf"
    paths = export_zotero(p, tmp_path)
    content = paths[0].read_text()
    assert "url = {" in content


def test_export_zotero_url_not_included_when_pdf(tmp_path):
    p = make_paper(with_pdf=True)
    p.pdf_url = "https://arxiv.org/pdf/1234.5678.pdf"
    paths = export_zotero(p, tmp_path)
    content = paths[0].read_text()
    assert "url = {" not in content


def test_export_zotero_valid_bibtex(tmp_path):
    p = make_paper(with_pdf=True)
    paths = export_zotero(p, tmp_path)
    content = paths[0].read_text()
    assert content.startswith("@article{")
    assert content.strip().endswith("}")
