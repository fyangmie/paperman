from __future__ import annotations

from typing import Optional

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
            title=item.get("title", ""),
            authors=authors,
            journal=item.get("source", ""),
            year=int(item.get("pubdate", "").split()[-1]) if item.get("pubdate") else None,
            metadata_source="pubmed",
        )

    @staticmethod
    def _by_doi(doi: str) -> Optional[Paper]:
        return None

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
