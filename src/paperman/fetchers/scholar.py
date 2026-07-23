from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from loguru import logger

from paperman.models.paper import Paper, SourceType

SCHOLAR_URL = "https://scholar.google.com/scholar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

CHROME_PATH = Path.home() / ".cache" / "ms-playwright" / "chromium-1228" / "chrome-linux64" / "chrome"
_BLOCKED = False  # set True after a CAPTCHA, so next call directly uses Selenium


def search_scholar(query: str, limit: int = 10) -> list[dict]:
    global _BLOCKED
    if not _BLOCKED:
        results = _search_requests(query, limit)
        if results:
            return results
        _BLOCKED = True
        logger.info("Google Scholar blocked requests, falling back to Selenium...")

    return _search_selenium(query, limit) if CHROME_PATH.exists() else []


def _search_requests(query: str, limit: int = 10) -> list[dict]:
    results = []
    start = 0
    while len(results) < limit:
        try:
            resp = requests.get(
                SCHOLAR_URL, params={"q": query, "start": start, "hl": "en"},
                headers=HEADERS, timeout=15,
            )
        except requests.RequestException as e:
            logger.warning(f"Scholar request failed: {e}")
            break
        if "CAPTCHA" in resp.text or resp.status_code != 200:
            logger.warning("Google Scholar CAPTCHA or network block")
            return []
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


def _search_selenium(query: str, limit: int = 10) -> list[dict]:
    def _init():
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.binary_location = str(CHROME_PATH)
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        return uc.Chrome(options=options, version_main=149)

    driver = None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_init)
            driver = fut.result(timeout=25)
    except TimeoutError:
        logger.warning("Selenium init timed out (25s)")
        return []
    except Exception as e:
        logger.warning(f"Selenium init failed: {e}")
        return []

    results = []
    try:
        driver.set_page_load_timeout(20)
        driver.get(f"{SCHOLAR_URL}?q={query.replace(' ', '+')}&hl=en")
        import time
        time.sleep(3)
        if "CAPTCHA" in driver.page_source:
            logger.warning("Google Scholar CAPTCHA even via browser")
            return results
        if len(driver.page_source) < 500:
            logger.warning("Google Scholar unreachable (network block)")
            return results
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for paper in soup.find_all("div", class_="gs_r"):
            link_tag = paper.find("h3", class_="gs_rt")
            if not link_tag or not link_tag.find("a"):
                continue
            title = link_tag.get_text(separator=" ", strip=True)
            url = link_tag.find("a")["href"]
            pdf_div = paper.find("div", class_="gs_ggs gs_fl")
            pdf_link = pdf_div.find("a")["href"] if pdf_div and pdf_div.find("a") else None
            results.append({"title": title, "url": url, "pdf_url": pdf_link})
            if len(results) >= limit:
                break
    except Exception as e:
        logger.warning(f"Selenium search failed: {e}")
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
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
