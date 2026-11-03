from __future__ import annotations

from typing import Optional
import re
from urllib.parse import quote, urljoin, urlsplit, urldefrag
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
    max_candidates = 12
    # These article URLs require journal/article IDs that cannot be derived from
    # the DOI suffix alone. Discover their PDF links rather than guess an ID.
    landing_first = {"10.1093", "10.1210", "10.1242", "10.1084", "10.2337",
                     "10.1136", "10.1681", "10.2147", "10.21037", "10.1115"}
    pdf_path = re.compile(r"/(?:articlepdf|doi/(?:e?pdf|pdfdirect)|content/pdf|pdfft|article-pdf)/|/pdfft(?:$|[?])|\.pdf(?:$|[?])", re.I)
    excluded_link = re.compile(r"supplement|supporting|appendix|citation|reference|related|recommended", re.I)

    @staticmethod
    def _url(value: str, base: str = "") -> Optional[str]:
        if not isinstance(value, str):
            return None
        try:
            url = urldefrag(urljoin(base, value.strip()))[0]
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
                return None
            if parts.hostname in {"api.wiley.com", "api.elsevier.com"}:
                return None  # Separate authenticated API clients, not web PDF links.
            if parts.hostname == "pubs.rsc.org" and parts.scheme == "http":
                url = "https:" + url[len("http:"):]
            return url
        except ValueError:
            return None

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        """Compatibility API. The pipeline consumes iter_pdf_urls to try all."""
        return next(self.iter_pdf_urls(paper), None)

    def iter_pdf_urls(self, paper: Paper):
        """Lazily try deposited links, templates, then article landing pages."""
        if not paper.doi:
            return
        seen = set()
        for url in self._candidates(paper):
            normalized = self._url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            yield normalized
            if len(seen) >= self.max_candidates:
                return

    def _candidates(self, paper: Paper):
        for link in paper.fulltext_links:
            url = self._url(link.get("URL", ""))
            if url and (link.get("content-type", "").split(";")[0].strip().lower() == "application/pdf"
                        or self.pdf_path.search(url)):
                yield url

        prefix, _, suffix = paper.doi.partition("/")
        if prefix == "10.1016":
            for value in [paper.landing_url] + [x.get("URL", "") for x in paper.fulltext_links]:
                match = re.search(r"(?:/pii/|PII:)([A-Za-z0-9]+)", value)
                if match:
                    yield "https://www.sciencedirect.com/science/article/pii/" + match.group(1) + "/pdfft"
        elif prefix in PUBLISHER_PATTERNS and prefix not in self.landing_first:
            slug = suffix.split(".")[1] if prefix == "10.1371" and "." in suffix else ""
            yield PUBLISHER_PATTERNS[prefix].format(
                doi=quote(paper.doi, safe="/"), suffix=quote(suffix, safe="/"),
                journal=PLOS_JOURNALS.get(slug, slug))
        # A HEAD rejection is not proof that GET fails; let the actual PDF
        # request decide. This fallback applies even to previously unknown DOIs.
        yield from self._landing_urls(paper)

    def _landing_urls(self, paper: Paper):
        visited = set()
        for value in [paper.landing_url, "https://doi.org/" + quote(paper.doi or "", safe="/")]:
            url = self._url(value)
            if not url or url in visited:
                continue
            visited.add(url)
            response = http.get(url, timeout=20)
            if response is None:
                continue
            if b"%PDF" in response.content[:1024]:
                yield response.url
                continue
            final = self._url(response.url)
            if not final:
                continue
            # The resolver commonly redirects to the already parsed landing.
            if final in visited and final != url:
                continue
            visited.add(final)
            yield from self._page_urls(response, paper)

    def _page_urls(self, response, paper: Paper):
        soup = BeautifulSoup(response.text, "html.parser")
        canonical_dois = [m.get("content", "") for m in soup.find_all("meta")
                          if str(m.get("name", "")).lower() in {"citation_doi", "dc.identifier.doi"}]
        normalize = lambda value: re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I).lower()
        if canonical_dois and normalize(paper.doi or "") not in {normalize(d) for d in canonical_dois}:
            logger.debug("publisher: landing page DOI differs from requested article")
            return
        for meta in soup.find_all("meta"):
            if str(meta.get("name", "")).lower() == "citation_pdf_url":
                yield urljoin(response.url, meta.get("content", ""))
        for link in soup.find_all("link", href=True):
            if str(link.get("type", "")).lower() == "application/pdf":
                yield urljoin(response.url, link["href"])
        for anchor in soup.find_all("a", href=True):
            # Do not select a supplementary PDF or a reference-list PDF merely
            # because it shares the .pdf extension.
            context = " ".join([anchor.get_text(" ", strip=True), anchor["href"],
                                str(anchor.get("class", "")), str(anchor.get("id", ""))])
            containers = " ".join(str(node.get("class", "")) + " " + str(node.get("id", ""))
                                  for node in anchor.parents if getattr(node, "attrs", None))
            if self.excluded_link.search(context + " " + containers):
                continue
            if self.pdf_path.search(anchor["href"]):
                yield urljoin(response.url, anchor["href"])

    def _landing_pdf(self, paper: Paper) -> Optional[str]:
        # Compatibility for older helper scripts.
        return next((u for value in self._landing_urls(paper) if (u := self._url(value))), None)
