from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader
from paperman.utils.network import http


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
        resp = http.get("https://sci-hub.now.sh/", timeout=10)
        if resp is not None:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "sci-hub." in href:
                    logger.info(f"Sci-Hub mirror found: {href}")
                    return href.rstrip("/")

        for c in candidates:
            resp = http.get(c, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp is not None:
                return c
        return candidates[0]

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        doi = paper.doi
        if not doi:
            return None

        url = f"{self.base_url}/{doi}"
        resp = http.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        if resp is None:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            src = str(iframe["src"])
            return src if src.startswith("http") else f"https:{src}"

        emb = soup.find("embed", {"type": "application/pdf"})
        if emb and emb.get("src"):
            return str(emb["src"])

        return None
