from paperman.sources.classifier import classify, SourceType


def test_doi():
    src = classify("10.1126/science.aef0825")
    assert src.type == SourceType.doi
    assert src.doi == "10.1126/science.aef0825"


def test_doi_with_url():
    src = classify("https://doi.org/10.1038/s41586-026-10644-y")
    assert src.type == SourceType.doi
    assert src.doi == "10.1038/s41586-026-10644-y"


def test_pmid():
    src = classify("40296124")
    assert src.type == SourceType.pmid
    assert src.pmid == "40296124"


def test_arxiv_id():
    src = classify("2505.13400")
    assert src.type == SourceType.arxiv
    assert src.arxiv_id == "2505.13400"


def test_arxiv_url():
    src = classify("https://arxiv.org/abs/2505.13400")
    assert src.type == SourceType.arxiv
    assert src.arxiv_id == "2505.13400"


def test_title():
    src = classify("PIEZO1 controls liver regeneration")
    assert src.type == SourceType.title


def test_pubmed_url():
    src = classify("https://pubmed.ncbi.nlm.nih.gov/40296124/")
    assert src.type == SourceType.pmid
    assert src.pmid == "40296124"
