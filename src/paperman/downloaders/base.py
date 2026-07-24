from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from loguru import logger

from paperman.models.paper import Paper
from paperman.utils.network import http


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

        resp = http.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        if resp is None:
            return None

        body = resp.content
        # Valid PDFs may have leading whitespace or BOM; search for %PDF within first KB
        pdf_pos = body.find(b"%PDF")
        if pdf_pos >= 0 and pdf_pos < 1024 and len(body) > 10000:
            path = dest / f"{paper.safe_filename()}.pdf"
            path.write_bytes(body)
            return path

        logger.debug(f"  {self.name}: response not PDF ({len(body)} bytes, header={body[:20]})")
        return None
