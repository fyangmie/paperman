from __future__ import annotations

from typing import Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger

from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader


class SciHubDownloader(BaseDownloader):
    name = "scihub"
    priority = 3

    def __init__(self):
        import urllib3
        import warnings
        warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
        self.base_url = self._find_mirror()

    @staticmethod
    def _find_mirror() -> str:
        candidates = [
            "https://sci-hub.se",
            "https://sci-hub.ru",
            "https://sci-hub.st",
            "https://sci-hub.wf",
        ]
        try:
            resp = requests.get("https://sci-hub.now.sh/", timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "sci-hub." in href:
                    logger.info(f"Sci-Hub mirror found: {href}")
                    return href.rstrip("/")
        except Exception:
            pass

        for c in candidates:
            try:
                resp = requests.get(c, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    return c
            except Exception:
                continue
        return candidates[0]

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        doi = paper.doi
        if not doi:
            return None

        url = f"{self.base_url}/{doi}"
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
            soup = BeautifulSoup(resp.text, "html.parser")
            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                src = iframe["src"]
                return src if src.startswith("http") else f"https:{src}"

            # fallback: look for embed or direct PDF link
            emb = soup.find("embed", {"type": "application/pdf"})
            if emb and emb.get("src"):
                return emb["src"]

        except Exception as e:
            logger.warning(f"Sci-Hub failed for {doi}: {e}")
        return None
