from __future__ import annotations

from typing import Optional

import re
from configparser import ConfigParser
from pathlib import Path

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType
from paperman.utils.network import http


CONFIG_PATH = Path.home() / ".config" / "paperman" / "config.ini"


class PubMedFetcher(BaseFetcher):
    name = "pubmed"
    priority = 2

    @staticmethod
    def _ncbi_params(**kw) -> dict:
        cfg = ConfigParser()
        if CONFIG_PATH.exists():
            cfg.read(CONFIG_PATH)
            key = cfg.get("settings", "ncbi_api_key", fallback="")
            if key:
                kw["api_key"] = key
        return kw

    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        if source_type == SourceType.pmid:
            return self._by_pmid(identifier)
        if source_type == SourceType.doi:
            return self._by_doi(identifier)
        return None

    @staticmethod
    def _by_pmid(pmid: str) -> Optional[Paper]:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        resp = http.get(url, params=PubMedFetcher._ncbi_params(db="pubmed", id=pmid, retmode="json"))
        if resp is None:
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
        search = http.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=cls._ncbi_params(db="pubmed", term=query, retmax=limit, retmode="json"),
        )
        if search is None:
            return []
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        summary = http.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params=cls._ncbi_params(db="pubmed", id=",".join(ids), retmode="json"),
        )
        if summary is None:
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
    def search_europepmc(query: str, limit: int = 10) -> list[Paper]:
        """Search Europe PMC (includes preprints, broader coverage)."""
        resp = http.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "pageSize": limit, "format": "json"},
        )
        if resp is None:
            return []
        results: list[Paper] = []
        for item in resp.json().get("resultList", {}).get("result", []):
            doi = item.get("doi") or ""
            pmcid = item.get("pmcid") or ""
            pmid = item.get("pmid") or ""
            authors = [a.strip() for a in item.get("authorString", "").split(",") if a.strip()]
            results.append(Paper(
                source_type=SourceType.doi if doi else SourceType.pmid,
                source_id=doi or pmid,
                doi=doi or None,
                pmid=pmid or None,
                pmcid=pmcid or None,
                title=item.get("title", ""),
                authors=authors,
                journal=item.get("journalTitle", ""),
                year=int(item.get("firstPublicationDate", "0000")[:4]) if item.get("firstPublicationDate") else None,
                metadata_source="europepmc",
            ))
        return results

    @staticmethod
    def resolve_pmcid(doi: str) -> Optional[str]:
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        resp = http.get(url, params=PubMedFetcher._ncbi_params(ids=doi, format="json"))
        if resp is None:
            return None
        records = resp.json().get("records", [])
        if records and "pmcid" in records[0]:
            return records[0]["pmcid"]
        return None
