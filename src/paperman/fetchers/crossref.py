from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

from loguru import logger

from paperman.fetchers import BaseFetcher
from paperman.models.paper import Paper, SourceType
from paperman.utils.network import http


class CrossrefFetcher(BaseFetcher):
    name = "crossref"
    base = "https://api.crossref.org/works"
    priority = 1

    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        if source_type == SourceType.doi:
            return self._fetch_by_doi(identifier)
        if source_type == SourceType.title:
            return self._search_by_title(identifier)
        return None

    def _fetch_by_doi(self, doi: str) -> Optional[Paper]:
        os.environ["PAPERMAN_CURRENT_DOI"] = doi
        os.environ["PAPERMAN_CURRENT_SOURCE"] = "crossref"
        resp = http.get(f"{self.base}/{quote(doi, safe='')}")
        if resp is None:
            logger.warning(f"CrossRef: {doi} -> failed")
            return None

        data = resp.json().get("message", {})
        return self._parse(data, doi=doi)

    def _search_by_title(self, title: str) -> Optional[Paper]:
        resp = http.get(self.base, params={"query.title": title, "rows": 1})
        if resp is None:
            return None
        items = resp.json().get("message", {}).get("items", [])
        if not items:
            return None
        return self._parse(items[0])

    @staticmethod
    def _parse(data: dict, doi: str = "") -> Optional[Paper]:
        doi = doi or data.get("DOI", "")
        authors = []
        for au in data.get("author", []):
            given = au.get("given", "")
            family = au.get("family", "")
            authors.append(f"{given} {family}".strip())

        year = None
        for key in ("published-print", "published-online", "issued"):
            parts = data.get(key, {}).get("date-parts")
            if parts and len(parts[0]) > 0:
                year = int(parts[0][0])
                break

        return Paper(
            source_type=SourceType.doi,
            source_id=doi,
            doi=doi,
            title=data.get("title", [""])[0] if data.get("title") else "",
            authors=authors,
            journal=data.get("container-title", [""])[0] if data.get("container-title") else "",
            year=year,
            volume=data.get("volume", ""),
            issue=data.get("issue", ""),
            pages=data.get("page", ""),
            publisher=data.get("publisher", ""),
            metadata_source="crossref",
            fulltext_links=data.get("link", []),
            landing_url=data.get("resource", {}).get("primary", {}).get("URL", ""),
        )
