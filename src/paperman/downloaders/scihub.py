from __future__ import annotations
import os
from urllib.parse import quote, urljoin, urlsplit
from bs4 import BeautifulSoup
from paperman.downloaders.base import BaseDownloader
from paperman.utils.network import HTTPClient

class SciHubDownloader(BaseDownloader):
    name = "scihub"
    priority = 2

    def __init__(self):
        # No homepage request: availability is checked for the actual DOI.
        self.mirrors = ["https://sci-hub.ru", "https://sci-hub.st",
                        "https://sci-hub.se", "https://sci-hub.wf"]
        self.client = HTTPClient()
        self.client.sess.trust_env = False
        self.client.sess.proxies = {}
        self.client.sess.verify = os.environ.get("REQUESTS_CA_BUNDLE") or True
        self.proxy = os.environ.get("PAPERMAN_SCIHUB_PROXY", "")
        self.base_url = self.mirrors[0]

    @staticmethod
    def extract_urls(html, page_url):
        soup = BeautifulSoup(html, "html.parser")
        result = []
        for tag in soup.find_all(["iframe", "embed", "object", "a"]):
            value = tag.get("data") if tag.name == "object" else tag.get("href") if tag.name == "a" else tag.get("src")
            if not value:
                continue
            if tag.name == "a" and ".pdf" not in value.lower():
                continue
            url = urljoin(page_url, value)
            if urlsplit(url).scheme in ("https", "http") and url not in result:
                result.append(url)
        return result

    def iter_pdf_urls(self, paper):
        if not paper.doi:
            return
        # Keep each route active until its PDF candidates have been tried.
        for proxy in [""] + ([self.proxy] if self.proxy else []):
            self.client.sess.proxies = {"http": proxy, "https": proxy} if proxy else {}
            for mirror in self.mirrors:
                self.base_url = mirror
                url = mirror + "/" + quote(paper.doi, safe="/")
                response = self.client.get(url, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
                if response is None:
                    continue
                if b"%PDF" in response.content[:1024]:
                    yield response.url
                else:
                    for candidate in self.extract_urls(response.text, response.url):
                        yield candidate

    def get_pdf_url(self, paper):
        return next(self.iter_pdf_urls(paper), None)

    def download(self, paper, dest):
        if not paper.pdf_url:
            return None
        response = self.client.get(paper.pdf_url, timeout=30, headers={"User-Agent":"Mozilla/5.0"})
        if response is None:
            return None
        if b"%PDF" not in response.content[:1024] or len(response.content) <= 10000:
            return None
        path = dest / (paper.safe_filename() + ".pdf")
        path.write_bytes(response.content)
        return path
