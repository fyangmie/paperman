from __future__ import annotations


from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from paperman.models.paper import Paper

console = Console()


def print_paper(paper: Paper) -> None:
    table = Table(show_header=False, border_style="blue")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("Title", paper.title or "(unknown)")
    table.add_row("Authors", "; ".join(paper.authors[:5]) if paper.authors else "(unknown)")
    table.add_row("Journal", paper.journal or "(unknown)")
    table.add_row("Year", str(paper.year or ""))
    if paper.doi:
        table.add_row("DOI", paper.doi)
    if paper.pmid:
        table.add_row("PMID", paper.pmid)
    if paper.arxiv_id:
        table.add_row("arXiv", paper.arxiv_id)
    if paper.pdf_url:
        table.add_row("PDF URL", paper.pdf_url)
    if paper.pdf_path:
        table.add_row("Saved to", str(paper.pdf_path))
    if paper.metadata_source:
        table.add_row("Metadata", paper.metadata_source)
    if paper.pdf_source:
        table.add_row("PDF source", paper.pdf_source)
    console.print(Panel(table, title="Paper"))


class Spinner:
    def __init__(self, msg: str):
        self.msg = msg

    def __enter__(self):
        self.progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=console
        )
        self.progress.start()
        self.task = self.progress.add_task(self.msg)
        return self

    def __exit__(self, *args):
        self.progress.stop()
