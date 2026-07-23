from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

from paperman.models.paper import Paper


class BaseDownloader(ABC):
    name: str = "base"
    priority: int = 99

    @abstractmethod
    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        ...

    def download(self, paper: Paper, dest: Path) -> Optional[Path]:
        url = paper.pdf_url
        if not url:
            return None

        try:
            resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            body = resp.content
            if len(body) > 10000 and body[:4] == b"%PDF":
                path = dest / f"{paper.safe_filename()}.pdf"
                path.write_bytes(body)
                return path
            else:
                logger.debug(f"  {self.name}: response not PDF ({len(body)} bytes, header={body[:20]})")
        except requests.RequestException as e:
            logger.debug(f"  {self.name}: request failed: {e}")
        return None
