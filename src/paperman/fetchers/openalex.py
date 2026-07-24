from __future__ import annotations

from typing import Optional

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType
from paperman.utils.network import http


class OpenAlexFetcher(BaseFetcher):
    name = "openalex"
    priority = 4

    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        if source_type == SourceType.doi:
            return self._by_doi(identifier)
        if source_type == SourceType.title:
            return self._search(identifier)
        return None

    @staticmethod
    def _by_doi(doi: str) -> Optional[Paper]:
        resp = http.get(f"https://api.openalex.org/works/doi:{doi}")
        if resp is None:
            return None
        data = resp.json()
        return OpenAlexFetcher._parse(data, doi)

    @staticmethod
    def _search(query: str) -> Optional[Paper]:
        resp = http.get(
            "https://api.openalex.org/works",
            params={"search": query, "per_page": 1},
        )
        if resp is None:
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        return OpenAlexFetcher._parse(results[0])

    @staticmethod
    def search_by_query(query: str, limit: int = 10) -> list[Paper]:
        resp = http.get(
            "https://api.openalex.org/works",
            params={"search": query, "per_page": limit},
        )
        if resp is None:
            return []
        papers: list[Paper] = []
        for item in resp.json().get("results", []):
            paper = OpenAlexFetcher._parse(item)
            if paper:
                papers.append(paper)
        return papers

    @staticmethod
    def _parse(data: dict, doi: str = "") -> Optional[Paper]:
        doi = doi or (data.get("doi") or "").replace("https://doi.org/", "")
        if not doi:
            return None

        authors = []
        for au in data.get("authorships", []):
            name = au.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        concepts = [c["display_name"] for c in data.get("concepts", []) if c.get("score", 0) > 0.3]

        oa = data.get("open_access", {})
        pdf_url = oa.get("oa_url") if oa.get("is_oa") else None

        return Paper(
            source_type=SourceType.doi,
            source_id=doi,
            doi=doi,
            title=data.get("title", ""),
            authors=authors,
            journal=(data.get("primary_location") or {}).get("source", {}).get("display_name", ""),
            year=data.get("publication_year"),
            volume=(data.get("biblio") or {}).get("volume", ""),
            issue=(data.get("biblio") or {}).get("issue", ""),
            pages=(data.get("biblio") or {}).get("pages", ""),
            publisher=(data.get("primary_location") or {}).get("source", {}).get("publisher", ""),
            abstract=data.get("abstract_inverted_index", "") and OpenAlexFetcher._decode_abstract(data["abstract_inverted_index"]) or "",
            keywords=concepts,
            pdf_url=pdf_url,
            metadata_source="openalex",
        )

    @staticmethod
    def _decode_abstract(inverted_index: dict) -> str:
        if not inverted_index:
            return ""
        words: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                words.append((pos, word))
        words.sort(key=lambda x: x[0])
        return " ".join(w for _, w in words)
