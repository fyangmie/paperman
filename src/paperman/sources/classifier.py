from __future__ import annotations

import re
from dataclasses import dataclass

from paperman.models.paper import SourceType


@dataclass
class Source:
    raw: str
    type: SourceType = SourceType.unknown
    cleaned: str = ""
    doi: str = ""
    pmid: str = ""
    arxiv_id: str = ""
    url: str = ""

    def __post_init__(self):
        if not self.cleaned:
            self.cleaned = self.raw.strip()


DOI_PATTERN = re.compile(r"^10\.\d{4,}/.+$")
ARXIV_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_URL_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")
PMID_PATTERN = re.compile(r"^\d{1,8}$")
DOI_URL_PATTERN = re.compile(r"(?:doi\.org|doi\.)(?:/|%2F)(10\.\d{4,}/[^\s?#]+)")
PUBMED_URL_PATTERN = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,8})")


def classify(raw: str) -> Source:
    src = Source(raw=raw)

    # DOI URL → extract DOI
    m = DOI_URL_PATTERN.search(raw)
    if m:
        src.type = SourceType.doi
        src.doi = m.group(1).rstrip("/")
        src.cleaned = raw
        return src

    # PubMed URL → extract PMID
    m = PUBMED_URL_PATTERN.search(raw)
    if m:
        src.type = SourceType.pmid
        src.pmid = m.group(1)
        src.cleaned = raw
        return src

    # arXiv URL → extract ID
    m = ARXIV_URL_PATTERN.search(raw)
    if m:
        src.type = SourceType.arxiv
        src.arxiv_id = m.group(1)
        src.cleaned = raw
        return src

    # bare arXiv ID
    if ARXIV_PATTERN.fullmatch(raw.strip()):
        src.type = SourceType.arxiv
        src.arxiv_id = raw.strip()
        return src

    # bare DOI
    if DOI_PATTERN.match(raw.strip()):
        src.type = SourceType.doi
        src.doi = raw.strip()
        return src

    # bare PMID
    if PMID_PATTERN.match(raw.strip()):
        src.type = SourceType.pmid
        src.pmid = raw.strip()
        return src

    # URL
    if raw.startswith(("http://", "https://")):
        src.type = SourceType.url
        src.url = raw
        return src

    # fallback: title
    src.type = SourceType.title
    return src
