from __future__ import annotations

import time
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader
from paperman.downloaders.arxiv import ArxivDownloader
from paperman.downloaders.pmc import PMCDownloader
from paperman.downloaders.publisher import PublisherDownloader
from paperman.downloaders.scihub import SciHubDownloader

_RETRY_WAIT = 3  # seconds


class DownloadPipeline:
    def __init__(self, sources=None):
        names = sources if sources is not None else os.environ.get(
            "PAPERMAN_SOURCES", "arxiv,pmc,scihub,publisher,arxiv_title").split(",")
        names = [name.strip() for name in names]
        allowed = {"arxiv": ArxivDownloader, "pmc": PMCDownloader,
                   "scihub": SciHubDownloader, "publisher": PublisherDownloader}
        if not names or len(set(names)) != len(names) or any(n not in {*allowed, "arxiv_title"} for n in names):
            raise ValueError("Sources must be unique known source names")
        if "arxiv_title" in names and names[-1] != "arxiv_title":
            raise ValueError("arxiv_title must be last (after ordinary-source retries)")
        self.title_fallback = "arxiv_title" in names
        self.downloaders: list[BaseDownloader] = [allowed[n]() for n in names if n in allowed]

    def download(self, paper: Paper, dest: Path, retries: Optional[int] = None) -> Optional[Path]:
        from paperman.progress import stage
        retries = int(os.environ.get("PAPERMAN_RETRIES", "1")) if retries is None else retries
        if retries < 0:
            raise ValueError("retries must be nonnegative")
        dest.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, retries + 2):
            for dl in self.downloaders:
                os.environ["PAPERMAN_CURRENT_DOI"] = paper.doi or ""
                os.environ["PAPERMAN_CURRENT_SOURCE"] = dl.name
                stage("pdf", source=dl.name, outcome="started", round=attempt)
                logger.info(f"Trying {dl.name}...")
                urls = (dl.iter_pdf_urls(paper) if hasattr(dl, "iter_pdf_urls")
                        else iter([dl.get_pdf_url(paper)]))
                for url in urls:
                    if not url:
                        continue
                    paper.pdf_url = url
                    result = dl.download(paper, dest)
                    if result:
                        paper.pdf_path = result
                        paper.pdf_source = dl.name
                        logger.info(f"Downloaded via {dl.name}: {result}")
                        stage("pdf", source=dl.name, outcome="saved", round=attempt)
                        return result
                stage("pdf", source=dl.name, outcome="exhausted", round=attempt)
                logger.debug(f"{dl.name}: candidates exhausted")

            if attempt <= retries:
                logger.info(f"Retrying in {_RETRY_WAIT}s (attempt {attempt}/{retries})...")
                time.sleep(_RETRY_WAIT)
                from paperman.utils.network import http
                http.reload_proxy()
            else:
                break

        # Only after all ordinary sources and their retries have failed.
        if not self.title_fallback:
            return None
        stage("pdf", source="arxiv_title", outcome="started")
        from paperman.fetchers.arxiv import ArxivFetcher
        os.environ["PAPERMAN_CURRENT_SOURCE"] = "arxiv_title"
        candidate = ArxivFetcher().find_matching_preprint(paper)
        if candidate and candidate.arxiv_id:
            candidate.pdf_url = f"https://arxiv.org/pdf/{candidate.arxiv_id}.pdf"
            candidate.title = paper.title
            result = ArxivDownloader().download(candidate, dest)
            if result:
                paper.arxiv_id = candidate.arxiv_id
                paper.pdf_url = candidate.pdf_url
                paper.pdf_path = result
                paper.pdf_source = "arxiv_title"
                stage("pdf", source="arxiv_title", outcome="saved")
                return result
        stage("pdf", source="arxiv_title", outcome="exhausted")
        logger.warning("All downloaders and arXiv title lookup failed")
        return None
