from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
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

    fulltext_links: list[dict] = Field(default_factory=list)
    landing_url: str = ""
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

        fields = [
            ("author", f"{{{esc(author_str)}}}"),
            ("title", f"{{{esc(self.title)}}}"),
            ("journal", f"{{{esc(self.journal)}}}"),
        ]
        if self.year:
            fields.append(("year", str(self.year)))
        if self.volume:
            fields.append(("volume", f"{{{self.volume}}}"))
        if self.issue:
            fields.append(("number", f"{{{self.issue}}}"))
        if self.pages:
            fields.append(("pages", f"{{{self.pages}}}"))
        if self.doi:
            fields.append(("doi", f"{{{self.doi}}}"))
        if self.pmid:
            fields.append(("pmid", f"{{{self.pmid}}}"))
        if self.pmcid:
            fields.append(("pmcid", f"{{{self.pmcid}}}"))
        if self.publisher:
            fields.append(("publisher", f"{{{esc(self.publisher)}}}"))
        if self.keywords:
            fields.append(("keywords", f"{{{', '.join(self.keywords)}}}"))

        lines = [f"@article{{{citekey},"]
        for name, val in fields:
            lines.append(f"  {name} = {val},")
        lines.append("}")
        return "\n".join(lines)

    def to_yaml(self) -> str:
        data: dict = {
            "title": self.title,
        }
        if self.authors:
            data["authors"] = self.authors
        if self.journal:
            data["journal"] = self.journal
        if self.year:
            data["year"] = self.year
        if self.doi:
            data["doi"] = self.doi
        if self.pmid:
            data["pmid"] = self.pmid
        if self.pmcid:
            data["pmcid"] = self.pmcid
        if self.arxiv_id:
            data["arxiv"] = self.arxiv_id
        if self.pdf_path:
            data["file"] = str(self.pdf_path)
        if self.abstract:
            abbr = self.abstract[:150].replace("\n", " ")
            data["abstract"] = f"{abbr}..."
        sources: dict = {}
        if self.metadata_source:
            sources["metadata"] = self.metadata_source
        if self.pdf_source:
            sources["pdf"] = self.pdf_source
        if sources:
            data["sources"] = sources
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
