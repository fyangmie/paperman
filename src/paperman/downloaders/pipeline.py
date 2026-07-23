from __future__ import annotations

import time
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
    def __init__(self):
        self.downloaders: list[BaseDownloader] = sorted(
            [ArxivDownloader(), PMCDownloader(), PublisherDownloader(), SciHubDownloader()],
            key=lambda d: d.priority,
        )

    def download(self, paper: Paper, dest: Path, retries: int = 1) -> Optional[Path]:
        dest.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, retries + 2):
            for dl in self.downloaders:
                logger.info(f"Trying {dl.name}...")
                url = dl.get_pdf_url(paper)
                if url:
                    logger.info(f"  URL found: {url[:100]}")
                    paper.pdf_url = url
                    result = dl.download(paper, dest)
                    if result:
                        paper.pdf_path = result
                        paper.pdf_source = dl.name
                        logger.info(f"  Downloaded: {result}")
                        return result
                    logger.warning(f"  {dl.name}: URL found but download failed")
                else:
                    logger.debug(f"  {dl.name}: no URL")

            if attempt <= retries:
                logger.info(f"Retrying in {_RETRY_WAIT}s (attempt {attempt}/{retries})...")
                time.sleep(_RETRY_WAIT)
                from paperman.utils.network import http
                http.reload_proxy()
            else:
                break

        logger.warning("All downloaders failed")
        return None
