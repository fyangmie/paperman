from __future__ import annotations

from typing import Optional


from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader


class ArxivDownloader(BaseDownloader):
    name = "arxiv"
    priority = 0  # highest

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        if paper.arxiv_id:
            return f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
        return paper.pdf_url if paper.pdf_url and "arxiv.org" in paper.pdf_url else None
