from __future__ import annotations

from typing import Optional

import re

import requests

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType


class PubMedFetcher(BaseFetcher):
    name = "pubmed"
    priority = 2

    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        if source_type == SourceType.pmid:
            return self._by_pmid(identifier)
        if source_type == SourceType.doi:
            return self._by_doi(identifier)
        return None

    @staticmethod
    def _by_pmid(pmid: str) -> Optional[Paper]:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        resp = requests.get(url, params={"db": "pubmed", "id": pmid, "retmode": "json"}, timeout=30)
        if resp.status_code != 200:
            return None
        data = resp.json().get("result", {})
        item = data.get(pmid)
        if not item:
            return None

        authors = [au.get("name", "") for au in item.get("authors", [])]
        return Paper(
            source_type=SourceType.pmid,
            source_id=pmid,
            pmid=pmid,
            doi=PubMedFetcher._clean_doi(item.get("elocationid", "")),
            title=item.get("title", ""),
            authors=authors,
            journal=item.get("source", ""),
            year=PubMedFetcher._extract_year(item.get("pubdate", "")),
            metadata_source="pubmed",
        )

    @staticmethod
    def _by_doi(doi: str) -> Optional[Paper]:
        return None

    @staticmethod
    def _extract_year(pubdate: str) -> int | None:
        if not pubdate:
            return None
        m = re.search(r"(\d{4})", pubdate)
        return int(m.group(1)) if m else None

    @staticmethod
    def _clean_doi(elocationid: str) -> str:
        """Extract clean DOI from NCBI's elocationid field.
        Handles: 'doi: 10.xxx/xxx', 'pii: Sxxx. 10.xxx/xxx', '10.xxx/xxx'
        """
        if not elocationid:
            return ""
        m = re.search(r"(10\.\d{4,}/[^\s,;]+)", elocationid)
        return m.group(1) if m else ""

    @classmethod
    def search_by_query(cls, query: str, limit: int = 10) -> list[Paper]:
        search = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"},
            timeout=30,
        )
        if search.status_code != 200:
            return []
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        summary = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=30,
        )
        if summary.status_code != 200:
            return []

        results = []
        data = summary.json().get("result", {})
        for pmid in ids:
            item = data.get(pmid)
            if not item:
                continue
            authors = [au.get("name", "") for au in item.get("authors", [])]
            results.append(Paper(
                source_type=SourceType.pmid,
                source_id=pmid,
                pmid=pmid,
                doi=cls._clean_doi(item.get("elocationid", "")),
                title=item.get("title", ""),
                authors=authors,
                journal=item.get("source", ""),
                year=cls._extract_year(item.get("pubdate", "")),
                metadata_source="pubmed",
            ))
        return results

    @staticmethod
    def resolve_pmcid(doi: str) -> Optional[str]:
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        resp = requests.get(url, params={"ids": doi, "format": "json"}, timeout=30)
        if resp.status_code != 200:
            return None
        records = resp.json().get("records", [])
        if records and "pmcid" in records[0]:
            return records[0]["pmcid"]
        return None
