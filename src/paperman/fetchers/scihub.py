from __future__ import annotations

from typing import Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger

from paperman.fetchers import BaseFetcher
from paperman.models import Paper


class SciHubFetcher(BaseFetcher):
    name = "scihub"

    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers = {"User-Agent": "Mozilla/5.0"}
        self.base_url = self._find_available()

    @staticmethod
    def _find_available() -> str:
        try:
            resp = requests.get("https://sci-hub.now.sh/", timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if "sci-hub." in a["href"]:
                    return a["href"].rstrip("/")
        except Exception:
            pass
        return "https://sci-hub.se"

    def _classify(self, identifier: str) -> str:
        if identifier.startswith(("http://", "https://")):
            return "url-direct" if identifier.endswith("pdf") else "url-non-direct"
        if identifier.isdigit():
            return "pmid"
        return "doi"

    def fetch_by_doi(self, doi: str) -> Optional[Paper]:
        url = f"{self.base_url}/{doi}"
        try:
            resp = self.sess.get(url, verify=False, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")
            iframe = soup.find("iframe")
            pdf_url = None
            if iframe:
                src = iframe.get("src", "")
                pdf_url = src if not src.startswith("//") else f"http:{src}"
            return Paper(
                doi=doi,
                pdf_url=pdf_url,
                source="scihub",
            )
        except Exception as e:
            logger.warning(f"Sci-Hub fetch failed for {doi}: {e}")
            return None

    def fetch_by_query(self, query: str, limit: int = 5) -> list[Paper]:
        return []

    def download_pdf(self, paper: Paper, dest: str) -> Optional[str]:
        """Download PDF from Sci-Hub, return file path."""
        if not paper.pdf_url:
            return None
        try:
            resp = self.sess.get(paper.pdf_url, verify=False, timeout=60)
            if "application/pdf" in resp.headers.get("Content-Type", ""):
                path = f"{dest}/{paper.doi.replace('/', '_')}.pdf"
                with open(path, "wb") as f:
                    f.write(resp.content)
                return path
        except Exception as e:
            logger.warning(f"Sci-Hub PDF download failed: {e}")
        return None
