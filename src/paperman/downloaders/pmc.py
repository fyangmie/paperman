from __future__ import annotations

from typing import Optional


from paperman.models.paper import Paper
from paperman.downloaders.base import BaseDownloader


class PMCDownloader(BaseDownloader):
    name = "pmc"
    priority = 1

    def get_pdf_url(self, paper: Paper) -> Optional[str]:
        if paper.pmcid:
            return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmcid}/pdf/"
        return None
