from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import requests

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType


ARXIV_API = "http://export.arxiv.org/api/query"


class ArxivFetcher(BaseFetcher):
    name = "arxiv"
    priority = 3

    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        if source_type == SourceType.arxiv:
            return self._fetch_by_id(identifier)
        if source_type == SourceType.doi:
            return None
        if source_type == SourceType.title:
            return self._search(identifier)
        return None

    def _fetch_by_id(self, arxiv_id: str) -> Optional[Paper]:
        arxiv_id = arxiv_id.split("v")[0]  # strip version
        resp = requests.get(f"{ARXIV_API}?id_list={arxiv_id}&max_results=1", timeout=30)
        if resp.status_code != 200:
            return None
        return self._parse_entry(self._first_entry(resp.text), arxiv_id)

    def _search(self, query: str) -> Optional[Paper]:
        resp = requests.get(
            ARXIV_API,
            params={"search_query": f"all:{query}", "max_results": 5, "sortBy": "relevance"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        entry = self._first_entry(resp.text)
        if entry is None:
            return None

        # extract ID from the <id> tag
        id_tag = entry.find("a:id", _ns)
        arxiv_id = ""
        if id_tag is not None:
            arxiv_id = id_tag.text.split("/")[-1] if id_tag.text else ""
        return self._parse_entry(entry, arxiv_id)

    @staticmethod
    def _first_entry(xml: str):
        root = ET.fromstring(xml)
        return root.find("a:entry", _ns)

    @staticmethod
    def _parse_entry(entry, arxiv_id: str) -> Optional[Paper]:
        if entry is None:
            return None

        def _txt(tag: str) -> str:
            el = entry.find(tag, _ns)
            return el.text.strip().replace("\n", " ") if el is not None and el.text else ""

        doi_link = entry.find('a:link[@title="doi"]', _ns)
        doi = ""
        if doi_link is not None:
            doi = doi_link.get("href", "").replace("https://doi.org/", "")

        pdf_link = entry.find('a:link[@title="pdf"]', _ns)
        pdf_url = pdf_link.get("href") if pdf_link is not None else f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        authors = []
        for au in entry.findall("a:author", _ns):
            name = au.find("a:name", _ns)
            if name is not None and name.text:
                authors.append(name.text)

        return Paper(
            source_type=SourceType.arxiv,
            source_id=arxiv_id,
            arxiv_id=arxiv_id,
            doi=doi,
            title=_txt("a:title"),
            authors=authors,
            abstract=_txt("a:summary"),
            pdf_url=pdf_url,
            metadata_source="arxiv",
        )


_ns = {"a": "http://www.w3.org/2005/Atom"}
