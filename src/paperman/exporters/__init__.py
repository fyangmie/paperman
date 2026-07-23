from __future__ import annotations

from pathlib import Path

from paperman.models.paper import Paper


def save_yaml(paper: Paper, dest: Path) -> Path:
    path = dest / f"{paper.safe_filename()}.yaml"
    path.write_text(paper.to_yaml())
    return path


def save_bibtex(paper: Paper, dest: Path) -> Path:
    path = dest / f"{paper.safe_filename()}.bib"
    path.write_text(paper.bibtex())
    return path


def export_zotero(paper: Paper, dest: Path) -> list[Path]:
    """Export paper as BibTeX + PDF pair for Zotero auto-import.

    Creates two files in the destination folder:
      {title}.bib  — Better BibTeX with relative file attachment path
      {title}.pdf  — (must be placed in same folder by caller)

    Zotero's 'Enable automated attachment import' will pick up
    .bib + .pdf pairs and auto-import them into your library.
    """
    saved = []
    dest.mkdir(parents=True, exist_ok=True)

    name = paper.safe_filename()
    bib_path = dest / f"{name}.bib"
    pdf_rel = f"{name}.pdf" if paper.pdf_path else None

    bib = paper.bibtex()

    # Append local file attachment for Zotero (relative path to PDF in same dir)
    lines = [bib.strip().rstrip("}").rstrip()]
    if pdf_rel:
        lines.append(f",\n  file = {{{pdf_rel}}}")
    if paper.pmcid:
        lines.append(f",\n  pmcid = {{{paper.pmcid}}}")
    if paper.pdf_url and not pdf_rel:
        lines.append(f",\n  url = {{{paper.pdf_url}}}")
    lines.append("\n}")

    bib_path.write_text("".join(lines))
    saved.append(bib_path)

    return saved
