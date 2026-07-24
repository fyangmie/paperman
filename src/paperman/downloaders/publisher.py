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
    "10.1371":  "https://journals.plos.org/{journal}/article/file?id={doi}",
    "10.15252": "https://www.embopress.org/doi/pdf/{doi}",
    "10.1242":  "https://journals.biologists.com/{doi}/article-pdf",
    "10.1101":  "https://www.biorxiv.org/content/{doi}.full.pdf",
    "10.1073":  "https://www.pnas.org/doi/pdf/{doi}",
    "10.1084":  "https://rupress.org/jem/article-pdf/{doi}",
    "10.2337":  "https://diabetes.diabetesjournals.org/doi/pdf/{doi}",
    "10.1056":  "https://www.nejm.org/doi/pdf/{doi}",
    "10.1136":  "https://heart.bmj.com/content/{doi}.pdf",
    "10.1152":  "https://journals.physiology.org/doi/pdf/{doi}",
    "10.1158":  "https://cancerres.aacrjournals.org/content/{doi}.pdf",
    "10.4049":  "https://www.jimmunol.org/content/{doi}.full.pdf",
    "10.1681":  "https://jasn.asnjournals.org/content/{doi}.full.pdf",
    "10.1200":  "https://ascopubs.org/doi/pdf/{doi}",
    "10.4161":  "https://www.tandfonline.com/doi/pdf/{doi}",
    "10.2147":  "https://www.dovepress.com/getfile.php?file={suffix}",
    "10.3892":  "https://www.spandidos-publications.com/{doi}/download",
    "10.21037": "https://atm.amegroups.com/article/view/{doi}/pdf",
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

        # Extract journal slug for PLOS (10.1371/journal.pbio.XXX → pbio)
        journal = suffix.split(".")[0] if prefix == "10.1371" else ""

        url = pattern.format(doi=doi, suffix=suffix, journal=journal)

        # HEAD check: only skip on 404 (pattern wrong), let 403/401/302 pass
        resp = http.head(url)
        if resp is not None and resp.status_code == 404:
            logger.debug(f"  publisher: {url[:70]} -> 404, skipping")
            return None

        return url
