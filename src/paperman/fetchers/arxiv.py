from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType
from paperman.utils.network import http


ARXIV_API = "https://export.arxiv.org/api/query"


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
        resp = http.get(f"{ARXIV_API}?id_list={arxiv_id}&max_results=1")
        if resp is None:
            return None
        return self._parse_entry(self._first_entry(resp.text), arxiv_id)

    def _search(self, query: str) -> Optional[Paper]:
        resp = http.get(ARXIV_API, params={"search_query": f"all:{query}", "max_results": 5, "sortBy": "relevance"})
        if resp is None:
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


    def find_matching_preprint(self, paper: Paper) -> Optional[Paper]:
        """Conservative title lookup; never accept an unrelated first hit."""
        import re
        import unicodedata
        from urllib.parse import urlsplit
        def normalize(value):
            value = unicodedata.normalize("NFKC", value or "").casefold()
            return "".join(c for c in value if c.isalnum())
        def doi_key(value):
            return (value or "").lower().strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        if not paper.title:
            return None
        title = " ".join(re.findall(r"\w+", paper.title, flags=re.UNICODE))
        response = http.get(ARXIV_API, params={
            "search_query": 'ti:"' + title + '"', "max_results": 10,
            "sortBy": "relevance"}, timeout=20)
        if response is None:
            return None
        try:
            entries = ET.fromstring(response.text).findall("a:entry", _ns)
        except ET.ParseError:
            return None
        exact, inferred = {}, {}
        for entry in entries:
            identifier = entry.findtext("a:id", default="", namespaces=_ns)
            parsed = urlsplit(identifier)
            if parsed.hostname not in ("arxiv.org", "www.arxiv.org") or "/abs/" not in parsed.path:
                continue
            arxiv_id = parsed.path.split("/abs/", 1)[1]
            candidate = self._parse_entry(entry, arxiv_id)
            if candidate is None:
                continue
            key = re.sub(r"v\d+$", "", arxiv_id)
            if paper.doi and candidate.doi:
                if doi_key(paper.doi) == doi_key(candidate.doi):
                    exact[key] = candidate
                continue  # Explicit DOI disagreement always rejects.
            authors = {normalize(a.split()[-1]) for a in paper.authors if a.split()}
            others = {normalize(a.split()[-1]) for a in candidate.authors if a.split()}
            if normalize(paper.title) == normalize(candidate.title) and authors & others:
                inferred[key] = candidate
        matches = exact or inferred
        return next(iter(matches.values())) if len(matches) == 1 else None

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

        doi = doi or _txt("{http://arxiv.org/schemas/atom}doi")

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
