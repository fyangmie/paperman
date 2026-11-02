from __future__ import annotations

from typing import Optional
import re
from urllib.parse import quote, urljoin, urlsplit
from bs4 import BeautifulSoup

from loguru import logger

from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader
from paperman.utils.network import http


PLOS_JOURNALS: dict[str, str] = {
    "pbio": "plosbiology",
    "pgen": "plosgenetics",
    "pone": "plosone",
    "pmed": "plosmedicine",
    "pntd": "plosntds",
    "pcbi": "ploscompbiol",
    "ppat": "plospathogens",
    "pclm": "plosclimate",
}

PUBLISHER_PATTERNS: dict[str, str] = {
    "10.1016":  "https://www.sciencedirect.com/science/article/pii/{suffix}/pdfft",
    "10.1038":  "https://www.nature.com/articles/{suffix}.pdf",
    "10.1126":  "https://www.science.org/doi/pdf/{doi}",
    "10.1161":  "https://www.ahajournals.org/doi/pdf/{doi}",
    "10.1186":  "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1007":  "https://link.springer.com/content/pdf/{doi}.pdf",
    "10.1093":  "https://academic.oup.com/{doi}/article-pdf",
    "10.3390":  "https://www.mdpi.com/{doi}/pdf",
    "10.1002":  "https://onlinelibrary.wiley.com/doi/pdf/{doi}",
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
    priority = 3

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        doi = paper.doi
        if not doi:
            logger.debug("  publisher: no DOI")
            return None

        # Deposited links are preferred to guessed publisher templates.
        for link in paper.fulltext_links:
            url = link.get("URL", "")
            if urlsplit(url).hostname in ("api.wiley.com", "api.elsevier.com"):
                continue
            if url.startswith("http://pubs.rsc.org/"):
                url = "https://" + url[len("http://"): ]
            if urlsplit(url).scheme in ("http", "https") and (
                link.get("content-type") == "application/pdf"
                or re.search(r"/(?:articlepdf|doi/pdf|content/pdf)/", url, re.I)
            ):
                return url
        if doi.startswith("10.1016/"):
            candidates = [paper.landing_url] + [
                x.get("URL", "") for x in paper.fulltext_links
            ]
            for candidate in candidates:
                match = re.search(r"(?:/pii/|PII:)([A-Za-z0-9]+)", candidate)
                if match:
                    return ("https://www.sciencedirect.com/science/article/pii/"
                            + match.group(1) + "/pdfft")
            return self._landing_pdf(paper)
        if doi.startswith("10.1039/"):
            return self._landing_pdf(paper)

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
        if prefix == "10.1371" and "." in suffix:
            slug = suffix.split(".")[1]
            journal = PLOS_JOURNALS.get(slug, slug)
        else:
            journal = ""

        url = pattern.format(doi=quote(doi, safe="/"), suffix=quote(suffix, safe="/"), journal=journal)

        # HEAD check for non-PLOS URLs: skip on 404 (pattern likely wrong)
        # PLOS returns 404 on HEAD for valid PDF URLs, so skip the check
        if prefix != "10.1371":
            resp = http.head(url)
            if resp is not None and resp.status_code == 404:
                logger.debug(f"  publisher: {url[:70]} -> 404, skipping")
                return None

        return url

    def _landing_pdf(self, paper: Paper) -> Optional[str]:
        url = paper.landing_url or "https://doi.org/" + quote(paper.doi or "", safe="/")
        resp = http.get(url)
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta and meta.get("content"):
            candidate = urljoin(resp.url, meta["content"])
            if urlsplit(candidate).scheme in ("http", "https"):
                return candidate
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"articlepdf|/doi/pdf/|/pdfft|/article-pdf/|\.pdf(?:$|[?#])", href, re.I):
                candidate = urljoin(resp.url, href)
                if urlsplit(candidate).scheme in ("http", "https"):
                    return candidate
        return None
