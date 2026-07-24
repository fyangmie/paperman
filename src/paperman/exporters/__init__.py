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
    """Export paper as BibTeX + PDF pair for Zotero auto-import."""
    saved = []
    dest.mkdir(parents=True, exist_ok=True)

    name = paper.safe_filename()
    bib_path = dest / f"{name}.bib"
    pdf_rel = f"{name}.pdf" if paper.pdf_path else None

    bib = paper.bibtex()
    # Insert extra fields before the closing "}"
    extra = []
    if pdf_rel:
        extra.append(f"  file = {{{pdf_rel}}}")
    if paper.pmcid:
        extra.append(f"  pmcid = {{{paper.pmcid}}}")
    if paper.pdf_url and not pdf_rel:
        extra.append(f"  url = {{{paper.pdf_url}}}")
    if extra:
        bib = bib.rstrip() + "\n" + ",\n".join(extra) + "\n}"

    bib_path.write_text(bib)
    saved.append(bib_path)

    return saved
