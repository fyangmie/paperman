from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from loguru import logger

from paperman.models.paper import Paper, SourceType

SCHOLAR_URL = "https://scholar.google.com/scholar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}


def search_scholar(query: str, limit: int = 10) -> list[dict]:
    results = []
    start = 0
    while len(results) < limit:
        try:
            resp = requests.get(
                SCHOLAR_URL,
                params={"q": query, "start": start, "hl": "en"},
                headers=HEADERS,
                timeout=15,
            )
        except requests.RequestException as e:
            logger.warning(f"Scholar request failed: {e}")
            break
        if "CAPTCHA" in resp.text or resp.status_code != 200:
            logger.warning("Google Scholar CAPTCHA or network block")
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        papers = soup.find_all("div", class_="gs_r")
        if not papers:
            break
        for paper in papers:
            link_tag = paper.find("h3", class_="gs_rt")
            if not link_tag or not link_tag.find("a"):
                continue
            title = link_tag.get_text(separator=" ", strip=True)
            url = link_tag.find("a")["href"]
            pdf_div = paper.find("div", class_="gs_ggs gs_fl")
            pdf_link = pdf_div.find("a")["href"] if pdf_div and pdf_div.find("a") else None
            results.append({"title": title, "url": url, "pdf_url": pdf_link})
            if len(results) >= limit:
                return results
        start += 10
    return results


def scholar_download(query: str, limit: int = 1) -> list[Paper]:
    results = search_scholar(query, limit)
    return [
        Paper(
            source_type=SourceType.url,
            source_id=r["url"],
            title=r["title"],
            pdf_url=r["pdf_url"],
            metadata_source="google_scholar",
        )
        for r in results
    ]
