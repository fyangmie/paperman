from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    doi = "doi"
    pmid = "pmid"
    arxiv = "arxiv"
    title = "title"
    url = "url"
    unknown = "unknown"


class Paper(BaseModel):
    source_type: SourceType = SourceType.unknown
    source_id: str = ""

    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    arxiv_id: Optional[str] = None

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    year: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    publisher: str = ""

    pdf_url: Optional[str] = None
    pdf_path: Optional[Path] = None
    metadata_source: str = ""
    pdf_source: str = ""

    def safe_filename(self, max_len: int = 100) -> str:
        name = self.title or self.doi or self.source_id or "paper"
        safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in name)
        safe = safe.strip("._ ")
        return safe[:max_len].rstrip() or "paper"

    def bibtex(self) -> str:
        first_author = self.authors[0].split()[-1] if self.authors else "Unknown"
        citekey = f"{first_author}{self.year or ''}"
        citekey = "".join(c for c in citekey if c.isalnum() or c in "-_")

        author_str = " and ".join(
            a if isinstance(a, str) else str(a) for a in self.authors
        ) if self.authors else ""

        def esc(s: str) -> str:
            return s.replace("{", "\\{").replace("}", "\\}").replace("&", "\\&")

        lines = [
            f"@article{{{citekey},",
            f"  author = {{{esc(author_str)}}},",
            f"  title = {{{esc(self.title)}}},",
            f"  journal = {{{esc(self.journal)}}}",
        ]
        if self.year:
            lines[-1] += ","
            lines.append(f"  year = {self.year}")
        if self.volume:
            lines[-1] += ","
            lines.append(f"  volume = {{{self.volume}}}")
        if self.issue:
            lines[-1] += ","
            lines.append(f"  number = {{{self.issue}}}")
        if self.pages:
            lines[-1] += ","
            lines.append(f"  pages = {{{self.pages}}}")
        if self.doi:
            lines[-1] += ","
            lines.append(f"  doi = {{{self.doi}}}")
        if self.pmid:
            lines[-1] += ","
            lines.append(f"  pmid = {{{self.pmid}}}")
        if self.pmcid:
            lines[-1] += ","
            lines.append(f"  pmcid = {{{self.pmcid}}}")
        if self.publisher:
            lines[-1] += ","
            lines.append(f"  publisher = {{{esc(self.publisher)}}}")
        if self.keywords:
            lines[-1] += ","
            lines.append(f"  keywords = {{{', '.join(self.keywords)}}}")
        lines.append("}")
        return "\n".join(lines)

    def to_yaml(self) -> str:
        def esc_yaml(s: str) -> str:
            return s.replace("'", "''").replace("\n", " ").replace("\r", "")
        lines = [f"title: '{esc_yaml(self.title)}'"]
        if self.authors:
            lines.append(f"authors: [{', '.join(self.authors)}]")
        if self.journal:
            lines.append(f"journal: {self.journal}")
        if self.year:
            lines.append(f"year: {self.year}")
        if self.doi:
            lines.append(f"doi: {self.doi}")
        if self.pmid:
            lines.append(f"pmid: {self.pmid}")
        if self.pmcid:
            lines.append(f"pmcid: {self.pmcid}")
        if self.arxiv_id:
            lines.append(f"arxiv: {self.arxiv_id}")
        if self.pdf_path:
            lines.append(f"file: {self.pdf_path}")
        if self.abstract:
            abbr = self.abstract[:150].replace("\n", " ")
            lines.append(f"abstract: '{abbr}...'")
        lines.append("sources:")
        if self.metadata_source:
            lines.append(f"  metadata: {self.metadata_source}")
        if self.pdf_source:
            lines.append(f"  pdf: {self.pdf_source}")
        return "\n".join(lines)
