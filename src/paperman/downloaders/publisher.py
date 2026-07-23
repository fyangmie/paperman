from __future__ import annotations

from typing import Optional

from loguru import logger

from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader
from paperman.utils.network import http


PUBLISHER_PATTERNS: dict[str, str] = {
    "10.1016":  "https://www.sciencedirect.com/science/article/pii/{suffix}",
    "10.1038":  "https://www.nature.com/articles/{suffix}.pdf",
    "10.1126":  "https://www.science.org/doi/pdf/{doi}",
    "10.1161":  "https://www.ahajournals.org/doi/pdf/{doi}",
    "10.1186":  "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1007":  "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1093":  "https://academic.oup.com/{doi}/article-pdf",
    "10.3390":  "https://www.mdpi.com/{doi}/pdf",
    "10.1111":  "https://onlinelibrary.wiley.com/doi/pdf/{doi}",
    "10.1021":  "https://pubs.acs.org/doi/pdf/{doi}",
    "10.1080":  "https://www.tandfonline.com/doi/pdf/{doi}",
    "10.1210":  "https://academic.oup.com/{doi}/article-pdf",
    "10.1172":  "https://www.jci.org/articles/view/{suffix}/pdf",
    "10.1371":  "https://journals.plos.org/plosone/article/file?id={doi}",
    "10.15252": "https://www.embopress.org/doi/pdf/{doi}",
    "10.1242":  "https://journals.biologists.com/{doi}/article-pdf",
    "10.1101":  "https://www.biorxiv.org/content/{doi}v1.full.pdf",
    "10.1073":  "https://www.pnas.org/doi/pdf/{doi}",
    "10.1084":  "https://rupress.org/jem/article-pdf/{doi}",
    "10.2337":  "https://diabetes.diabetesjournals.org/doi/pdf/{doi}",
}


class PublisherDownloader(BaseDownloader):
    name = "publisher"
    priority = 2

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        doi = paper.doi
        if not doi:
            logger.debug("  publisher: no DOI")
            return None

        prefix = None
        for key in sorted(PUBLISHER_PATTERNS, key=len, reverse=True):
            if doi.startswith(key):
                prefix = key
                break

        if prefix is None:
            logger.debug(f"  publisher: no pattern for {doi[:12]}...")
            return None

        suffix = doi.replace(prefix, "").lstrip("/")
        pattern = PUBLISHER_PATTERNS[prefix]
        url = pattern.format(doi=doi, suffix=suffix)

        # Quick header check: skip only on 4xx/5xx
        resp = http.head(url)
        if resp is None:
            logger.debug("  publisher: HEAD failed, returning URL anyway")
            return url
        if resp.status_code >= 400:
            logger.debug(f"  publisher: {url[:70]} -> {resp.status_code}")
            return None

        logger.debug(f"  publisher: {url[:70]} -> {resp.status_code}")
        return url
