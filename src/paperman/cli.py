from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from paperman.utils.log import setup_logger
from paperman.utils.console import console, print_paper, Spinner
from paperman.models.paper import SourceType, Paper
from paperman.sources.classifier import classify
from paperman.fetchers.crossref import CrossrefFetcher
from paperman.fetchers.arxiv import ArxivFetcher
from paperman.fetchers.pubmed import PubMedFetcher
from paperman.fetchers.openalex import OpenAlexFetcher
from paperman.downloaders.pipeline import DownloadPipeline
from paperman.exporters import save_yaml
from paperman.cache import PaperCache
from paperman.utils.network import http
from paperman.corpus.cli import app as corpus_app

app = typer.Typer(name="paperman", help="Enhanced academic paper downloader", no_args_is_help=True)
app.add_typer(corpus_app, name="corpus")
DEFAULT_OUTPUT = Path.home() / "Documents" / "papers"


@app.callback()
def callback(verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging")) -> None:
    setup_logger(verbose)


def _fetch_metadata(src_id: str, src_type: SourceType) -> Optional[Paper]:
    """Try all fetchers in priority order."""
    from paperman.progress import stage
    stage("metadata", outcome="started")
    fetchers: list = [CrossrefFetcher(), ArxivFetcher(), OpenAlexFetcher()]
    if src_type == SourceType.pmid:
        fetchers.insert(0, PubMedFetcher())
    for fetcher in fetchers:
        paper = fetcher.fetch(src_id, src_type)
        if paper:
            paper.source_id = src_id
            stage("metadata", outcome="found", source=fetcher.name, publisher=paper.publisher, journal=paper.journal, title=paper.title)
            logger.info(f"Metadata from {fetcher.name}")
            return paper
    return None


def _resolve_pmcid(paper: Paper) -> None:
    from paperman.progress import stage
    stage("pmc_lookup", outcome="started")
    if paper.doi and not paper.pmcid:
        pmcid = PubMedFetcher.resolve_pmcid(paper.doi)
        if pmcid:
            paper.pmcid = pmcid
            logger.info(f"PMCID: {pmcid}")


@app.command()
def download(
    identifier: str = typer.Argument(..., help="DOI / PMID / arXiv ID / URL / title"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o", help="Output directory"),
    bib: bool = typer.Option(False, "--bib", help="Export BibTeX"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Metadata only, skip PDF"),
    force: bool = typer.Option(False, "--force", "-f", help="Ignore cache, re-download"),
) -> None:
    """Download paper by DOI/PMID/arXiv ID with full metadata."""
    src = classify(identifier)
    console.print(f"[dim]Input: {src.type.value} → {src.cleaned[:80]}[/dim]")
    cache = PaperCache()

    # Check cache
    paper = None
    if not force and (src.type == SourceType.doi or src.type == SourceType.pmid):
        key = src.cleaned
        cached = cache.get(key) if src.type == SourceType.doi else cache.get_by_pmid(key)
        if cached:
            logger.info("Using cached metadata")
            paper = cached

    # Fetch metadata
    if paper is None:
        with Spinner("Fetching metadata..."):
            paper = _fetch_metadata(src.cleaned, src.type)
        if paper:
            cache.set(paper)
        else:
            logger.error("Metadata not found")
            raise typer.Exit(1)

    # Resolve PMCID
    if not paper.pmcid:
        with Spinner("Resolving PMCID..."):
            _resolve_pmcid(paper)

    print_paper(paper)

    # Download PDF
    if not no_pdf:
        pipeline = DownloadPipeline()
        result = pipeline.download(paper, output)

        if result:
            console.print(f"[green]✓[/] PDF: {result}")
            cache.update_pdf_path(paper.doi, result) if paper.doi else None
        else:
            sources_tried = ", ".join(d.name for d in pipeline.downloaders)
            console.print(f"[yellow]⚠[/] PDF not available (tried: {sources_tried})")
            console.print("   Try: vpn or `paperman config --set proxy ...`")

    # Save metadata
    output.mkdir(parents=True, exist_ok=True)
    yaml_path = output / f"{paper.safe_filename()}.yaml"
    yaml_path.write_text(paper.to_yaml())
    console.print(f"[green]✓[/] YAML: {yaml_path.name}")

    if bib:
        bib_path = output / f"{paper.safe_filename()}.bib"
        bib_path.write_text(paper.bibtex())
        console.print(f"[green]✓[/] Bib: {bib_path.name}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of results"),
    source: str = typer.Option("crossref", "--source", "-s", help="crossref | pubmed | eupmc | openalex | all"),
    download_flag: bool = typer.Option(False, "--download", "-d", help="Download after selecting"),
    csv: bool = typer.Option(False, "--csv", help="Output as CSV (easy to copy)"),
) -> None:
    """Search papers and interactively select to download."""
    from rich.table import Table

    results: list[Paper] = []

    with Spinner(f"Searching {source}..."):
        if source in ("crossref", "all"):
            resp = http.get("https://api.crossref.org/works", params={"query.title": query, "rows": limit})
            if resp is not None:
                for item in resp.json().get("message", {}).get("items", []):
                    authors = [f"{a.get('given','')} {a.get('family','')}".strip() for a in item.get("author", [])]
                    results.append(Paper(
                        source_type=SourceType.doi,
                        source_id=item.get("DOI", ""),
                        doi=item.get("DOI", ""),
                        title=item.get("title", [""])[0] if item.get("title") else "",
                        authors=authors,
                        journal=item.get("container-title", [""])[0] if item.get("container-title") else "",
                        year=int(item.get("published-print", {}).get("date-parts", [[0]])[0][0])
                            if item.get("published-print") else None,
                        metadata_source="crossref",
                    ))

        if source in ("pubmed", "all"):
            from paperman.fetchers.pubmed import PubMedFetcher
            results.extend(PubMedFetcher.search_by_query(query, limit))

        if source in ("eupmc", "all"):
            from paperman.fetchers.pubmed import PubMedFetcher
            results.extend(PubMedFetcher.search_europepmc(query, limit))

        if source in ("openalex", "all"):
            from paperman.fetchers.openalex import OpenAlexFetcher
            results.extend(OpenAlexFetcher.search_by_query(query, limit))

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    if csv:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["#", "Title", "Year", "DOI"])
        for i, p in enumerate(results, 1):
            w.writerow([i, p.title, p.year or "", p.doi or ""])
        console.print(buf.getvalue())
    else:
        table = Table(title=f"Results for '{query}'")
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", overflow="fold")
        table.add_column("Year", width=5)
        table.add_column("DOI", width=30, overflow="fold")
        for i, p in enumerate(results, 1):
            table.add_row(str(i), p.title, str(p.year or ""), p.doi or "")
        console.print(table)

    if download_flag:
        idx = typer.prompt("Select paper to download (number)", type=int, default=1)
        if 1 <= idx <= len(results):
            paper = results[idx - 1]
            if paper.doi:
                download(paper.doi)
            elif paper.title:
                download(paper.title)


@app.command(name="list")
def _list(
    query: str = typer.Option("", "--query", "-q", help="Filter by keyword"),
) -> None:
    """List cached/downloaded papers."""
    from rich.table import Table

    cache = PaperCache()
    papers = cache.search(query) if query else cache.list_all()

    if not papers:
        console.print("[yellow]No papers in cache[/yellow]")
        return

    table = Table(title=f"Cached papers{' matching: ' + query if query else ''}")
    table.add_column("DOI")
    table.add_column("Title", width=45)
    table.add_column("Year")
    table.add_column("PDF", width=10)

    for p in papers:
        table.add_row(
            p.doi or "",
            p.title[:45] if p.title else "(no title)",
            str(p.year or ""),
            "[green]✓[/]" if p.pdf_path else "[dim]—[/]",
        )
    console.print(table)


@app.command()
def show(
    identifier: str = typer.Argument(..., help="DOI or PMID"),
) -> None:
    """Show cached paper details."""
    cache = PaperCache()
    src = classify(identifier)
    paper = None
    if src.type == SourceType.doi:
        paper = cache.get(src.cleaned)
    elif src.type == SourceType.pmid:
        paper = cache.get_by_pmid(src.cleaned)

    if paper:
        print_paper(paper)
        if paper.abstract:
            console.print(f"\n[bold]Abstract:[/bold]\n{paper.abstract[:500]}")
        # Show Semantic Scholar citation data if DOI is available
        if paper.doi:
            resp = http.get(
                "https://api.semanticscholar.org/graph/v1/paper/DOI:" + paper.doi,
                params={"fields": "citationCount,influentialCitationCount"},
            )
            if resp is not None:
                s2 = resp.json()
                parts = []
                if s2.get("citationCount"):
                    parts.append(f"cited: [cyan]{s2['citationCount']}[/cyan]")
                if s2.get("influentialCitationCount"):
                    parts.append(f"influential: [cyan]{s2['influentialCitationCount']}[/cyan]")
                if parts:
                    console.print(f"\n[bold]Citations:[/bold] {' | '.join(parts)}")
    else:
        logger.error("Paper not found in cache")


@app.command()
def batch(
    file: Path = typer.Argument(..., help="File with DOIs/PMIDs, one per line"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o"),
    bib: bool = typer.Option(False, "--bib", help="Export BibTeX"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Skip already downloaded papers"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Metadata only, skip PDF"),
    log: Optional[Path] = typer.Option(None, "--log", "-l", help="Path to TSV log file"),
) -> None:
    """Batch download papers from a file."""
    if not file.exists():
        logger.error(f"File not found: {file}")
        raise typer.Exit(1)

    identifiers = [line.strip() for line in file.read_text().splitlines() if line.strip()]
    console.print(f"[dim]{len(identifiers)} identifiers loaded[/dim]")

    cache = PaperCache()
    if resume:
        skipped = 0
        filtered = []
        for id_ in identifiers:
            src = classify(id_)
            paper = cache.get(src.doi) if src.type == SourceType.doi and src.doi else cache.get_by_pmid(src.pmid) if src.pmid else None
            if paper and paper.pdf_path and paper.pdf_path.exists():
                skipped += 1
                continue
            filtered.append(id_)
        identifiers = filtered
        console.print(f"[dim]Resume: {skipped} already downloaded, {len(identifiers)} remaining[/dim]")
        if not identifiers:
            console.print("[green]All papers already downloaded[/green]")
            return

    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
    from paperman.downloaders.pipeline import DownloadPipeline

    logger.disable("paperman")

    success = 0
    results: list[dict] = []

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        redirect_stdout=True,
    )
    with progress:
        task = progress.add_task("", total=len(identifiers))
        output.mkdir(parents=True, exist_ok=True)
        for id_ in identifiers:
            progress.update(task, description=id_[:60])
            src = classify(id_)

            paper = _fetch_metadata(src.cleaned, src.type)
            if paper is None:
                console.print(f"[red]✗[/] {id_}  [dim]metadata not found[/dim]")
                results.append({"identifier": id_, "status": "failure", "pdf": "no", "yaml": "no"})
                progress.advance(task)
                continue

            cache.set(paper)
            _resolve_pmcid(paper)
            cache.set(paper)

            pdf_ok = "no"
            if not no_pdf:
                pipeline = DownloadPipeline()
                pdf_path = pipeline.download(paper, output)
                if pdf_path:
                    pdf_ok = "yes"
                    if paper.doi:
                        cache.update_pdf_path(paper.doi, pdf_path)

            yaml_path = output / f"{paper.safe_filename()}.yaml"
            yaml_path.write_text(paper.to_yaml())

            if bib:
                from paperman.exporters import save_bibtex
                save_bibtex(paper, output)

            success += 1
            icon = "[green]✓[/]" if pdf_ok == "yes" else "[yellow]✓[/]"
            console.print(f"{icon} {id_}  pdf:{pdf_ok}  yaml:yes")
            results.append({"identifier": id_, "status": "success", "pdf": pdf_ok, "yaml": "yes"})
            progress.advance(task)

    logger.enable("paperman")
    console.print(f"\nBatch done: [green]{success}[/green]/[dim]{len(identifiers)}[/dim] succeeded")

    if log:
        import csv
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["identifier", "status", "pdf", "yaml"])
            for r in results:
                w.writerow([r["identifier"], r["status"], r["pdf"], r["yaml"]])
        console.print(f"[green]✓[/] Log: {log}")


@app.command()
def import_bib(
    file: Path = typer.Argument(..., help="Path to .bib file"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Metadata only, skip PDF"),
) -> None:
    """Import papers from a BibTeX file."""
    if not file.exists():
        logger.error(f"File not found: {file}")
        raise typer.Exit(1)

    import bibtexparser
    with open(file) as f:
        db = bibtexparser.load(f)

    entries = db.entries if hasattr(db, "entries") else db.get("entries", [])
    console.print(f"[dim]{len(entries)} entries loaded from {file.name}[/dim]")

    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
    from paperman.downloaders.pipeline import DownloadPipeline

    logger.disable("paperman")

    cache = PaperCache()
    success = 0

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        redirect_stdout=True,
    )
    with progress:
        task = progress.add_task("", total=len(entries))
        output.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            doi = entry.get("doi", "").strip()
            pmid = entry.get("pmid", "").strip()
            title = entry.get("title", "").strip().rstrip(".").strip()
            identifier = doi or pmid or title
            if not identifier:
                progress.advance(task)
                continue

            progress.update(task, description=identifier[:60])
            src = classify(identifier)
            paper = _fetch_metadata(src.cleaned, src.type)
            if paper is None:
                console.print(f"[red]✗[/] {identifier}  [dim]metadata not found[/dim]")
                progress.advance(task)
                continue

            cache.set(paper)
            _resolve_pmcid(paper)
            cache.set(paper)

            # Attach local PDF from BibTeX file field if present
            bib_pdf = entry.get("file", "")
            pdf_attached = False
            if bib_pdf:
                pdf_candidates = [p.strip() for p in bib_pdf.replace(":", ";").split(";") if p.strip().endswith(".pdf")]
                for cand in pdf_candidates:
                    p = Path(cand)
                    if p.exists():
                        paper.pdf_path = p
                        if paper.doi:
                            cache.update_pdf_path(paper.doi, p)
                        pdf_attached = True
                        break

            pdf_ok = "yes" if pdf_attached else "no"
            if not no_pdf and not pdf_attached:
                pipeline = DownloadPipeline()
                pdf_path = pipeline.download(paper, output)
                if pdf_path:
                    pdf_ok = "yes"
                    if paper.doi:
                        cache.update_pdf_path(paper.doi, pdf_path)

            yaml_path = output / f"{paper.safe_filename()}.yaml"
            yaml_path.write_text(paper.to_yaml())
            success += 1
            icon = "[green]✓[/]" if pdf_ok == "yes" else "[yellow]✓[/]"
            console.print(f"{icon} {identifier}  pdf:{pdf_ok}  yaml:yes")
            progress.advance(task)

    logger.enable("paperman")
    console.print(f"\nImported: [green]{success}[/green]/[dim]{len(entries)}[/dim] papers")


@app.command()
def open_paper(
    identifier: str = typer.Argument(..., help="DOI / PMID / title"),
) -> None:
    """Open a downloaded paper's PDF with the system viewer."""
    import subprocess
    import webbrowser

    cache = PaperCache()
    src = classify(identifier)
    paper = None
    if src.type == SourceType.doi:
        paper = cache.get(src.cleaned)
    elif src.type == SourceType.pmid:
        paper = cache.get_by_pmid(src.cleaned)
    elif src.type == SourceType.title:
        papers = cache.search(identifier)
        if papers:
            paper = papers[0]

    if not paper or not paper.pdf_path or not paper.pdf_path.exists():
        logger.error("Paper PDF not found in cache")
        console.print(f"  Try: [dim]paperman download {identifier}[/dim]")
        raise typer.Exit(1)

    pdf_path = paper.pdf_path
    console.print(f"[green]✓[/] Opening: {pdf_path.name}")
    try:
        if webbrowser.open(str(pdf_path)) is False:
            subprocess.run(["xdg-open", str(pdf_path)], check=False)
    except Exception:
        subprocess.run(["xdg-open", str(pdf_path)], check=False)


@app.command()
def config(
    show_all: bool = typer.Option(False, "--show", help="Show current config"),
    set_key: str = typer.Option("", "--set", help="Config key"),
    set_val: str = typer.Option("", "--value", help="Config value"),
) -> None:
    """View or modify configuration."""
    from configparser import ConfigParser

    from paperman.utils.network import CONFIG_PATH
    cfg_path = CONFIG_PATH
    cfg_dir = cfg_path.parent
    cfg = ConfigParser()

    if cfg_path.exists():
        cfg.read(cfg_path)

    if set_key and set_val:
        cfg_dir.mkdir(parents=True, exist_ok=True)
        if "settings" not in cfg:
            cfg["settings"] = {}
        cfg["settings"][set_key] = set_val
        with open(cfg_path, "w") as f:
            cfg.write(f)
        console.print(f"[green]✓[/] {set_key} = {set_val}")

    default_output = cfg.get("settings", "output", fallback=str(DEFAULT_OUTPUT))
    proxy = cfg.get("settings", "proxy", fallback="")
    ncbi_key = cfg.get("settings", "ncbi_api_key", fallback="")
    masked_key = ncbi_key[:4] + "****" if ncbi_key else "(none)"
    console.print(f"[dim]Config file:[/dim] {cfg_path}")
    console.print(f"  output       = {default_output}")
    console.print(f"  proxy        = {proxy or '(none)'}")
    console.print(f"  proxy_mode   = {cfg.get('settings', 'proxy_mode', fallback='auto')}")
    console.print(f"  ncbi_api_key = {masked_key}")
    if proxy:
        from paperman.utils.network import http
        http.reload_proxy()


@app.command()
def stats() -> None:
    """Show download statistics (cache vs actual files)."""
    from rich.table import Table

    # Cache stats
    cache = PaperCache()
    papers = cache.list_all()
    cached_total = len(papers)
    cached_with_pdf = sum(1 for p in papers if p.pdf_path and p.pdf_path.exists())
    cached_stale = sum(1 for p in papers if p.pdf_path and not p.pdf_path.exists())

    # Disk stats (scan output directory from config or default)
    from configparser import ConfigParser
    from paperman.utils.network import CONFIG_PATH
    cfg_path = CONFIG_PATH
    cfg = ConfigParser()
    if cfg_path.exists():
        cfg.read(cfg_path)
    pdf_dir = Path(cfg.get("settings", "output", fallback=str(DEFAULT_OUTPUT)))
    disk_pdfs = list(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
    disk_total = len(disk_pdfs)
    disk_size_mb = sum(f.stat().st_size for f in disk_pdfs) / 1024 / 1024

    # Year distribution from disk files
    by_year: dict[int, int] = {}
    for p in papers:
        if p.year:
            by_year[p.year] = by_year.get(p.year, 0) + 1

    table = Table(title="Paperman Stats")
    table.add_column("Source", style="bold cyan")
    table.add_column("Count")
    table.add_row("Cache (metadata queried)", str(cached_total))
    table.add_row("  ├─ With valid PDF", f"[green]{cached_with_pdf}[/green]")
    if cached_stale:
        table.add_row("  └─ Stale (file deleted)", f"[yellow]{cached_stale}[/yellow]")
    table.add_row("")
    table.add_row(f"Files on disk ({pdf_dir})", str(disk_total))
    table.add_row("  └─ Total size", f"{disk_size_mb:.1f} MB")
    console.print(table)

    tables = []
    if by_year:
        years = Table(title="Cache by Year", show_header=False)
        years.add_column("Year")
        years.add_column("Count")
        for y in sorted(by_year, reverse=True):
            years.add_row(str(y), str(by_year[y]))
        tables.append(years)

    disk_by_year: dict[int, int] = {}
    for pdf in disk_pdfs:
        disk_name = pdf.stem
        for p in papers:
            if p.safe_filename() == disk_name and p.year:
                disk_by_year[p.year] = disk_by_year.get(p.year, 0) + 1
                break
    if disk_by_year:
        disk_years = Table(title="Disk by Year", show_header=False)
        disk_years.add_column("Year")
        disk_years.add_column("Count")
        for y in sorted(disk_by_year, reverse=True):
            disk_years.add_row(str(y), str(disk_by_year[y]))
        tables.append(disk_years)

    if len(tables) > 1:
        from rich.columns import Columns
        console.print(Columns(tables))
    elif tables:
        console.print(tables[0])


@app.command()
def scholar(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, "--limit", "-l", help="Max results"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o"),
    download_all: bool = typer.Option(False, "--download", "-d", help="Download all results"),
    csv: bool = typer.Option(False, "--csv", help="Output as CSV (easy to copy)"),
) -> None:
    """Search Google Scholar and download papers."""
    from rich.table import Table
    from paperman.fetchers.scholar import search_scholar

    with Spinner(f"Searching Google Scholar for '{query}'..."):
        results = search_scholar(query, limit)

    if not results:
        console.print("[yellow]No results or blocked by CAPTCHA[/yellow]")
        return

    if csv:
        import csv as csv_mod
        import io
        buf = io.StringIO()
        w = csv_mod.writer(buf)
        w.writerow(["#", "Title", "PDF"])
        for i, r in enumerate(results, 1):
            w.writerow([i, r["title"], "Yes" if r["pdf_url"] else ""])
        console.print(buf.getvalue())
    else:
        tw = console.width - 25
        table = Table(title=f"Google Scholar results for '{query}'")
        table.add_column("#", style="dim")
        table.add_column("Title", width=max(30, tw), overflow="fold")
        table.add_column("PDF", width=5)
        for i, r in enumerate(results, 1):
            table.add_row(str(i), r["title"], "[green]✓[/]" if r["pdf_url"] else "—")
        console.print(table)

    if download_all:
        for i, r in enumerate(results, 1):
            if r["pdf_url"]:
                console.print(f"\n[bold][{i}][/bold] {r['title'][:50]}")
                paper = Paper(
                    source_type=SourceType.url,
                    source_id=r["url"],
                    title=r["title"],
                    pdf_url=r["pdf_url"],
                    metadata_source="google_scholar",
                )
                pipeline = DownloadPipeline()
                with Spinner("Downloading..."):
                    result = pipeline.download(paper, output)
                if result:
                    console.print(f"[green]✓[/] {result.name}")
                save_yaml(paper, output)
    else:
        idx = typer.prompt("Download paper (number)", type=int, default=1)
        if 1 <= idx <= len(results):
            r = results[idx - 1]
            if r["pdf_url"]:
                paper = Paper(
                    source_type=SourceType.url,
                    source_id=r["url"],
                    title=r["title"],
                    pdf_url=r["pdf_url"],
                    metadata_source="google_scholar",
                )
                pipeline = DownloadPipeline()
                with Spinner("Downloading..."):
                    result = pipeline.download(paper, output)
                if result:
                    console.print(f"[green]✓[/] {result.name}")
                save_yaml(paper, output)
            else:
                logger.warning("No PDF link found in Google Scholar result")


@app.command()
def prune(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be removed"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    all: bool = typer.Option(False, "--all", "-a", help="Remove ALL cache entries"),
) -> None:
    """Remove stale or all cache entries."""
    cache = PaperCache()
    papers = cache.list_all()

    if all:
        if not dry_run:
            if not yes:
                typer.confirm(f"Remove all {len(papers)} cached entries?", abort=True)
            for p in papers:
                cache.remove(p.doi or "")
                if p.pdf_path and p.pdf_path.exists():
                    p.pdf_path.unlink()
            console.print(f"[green]✓[/] Cleared all {len(papers)} cache entries")
        else:
            console.print(f"[yellow]Would remove {len(papers)} entries:[/yellow]")
            for p in papers[:5]:
                console.print(f"  {p.doi or p.pmid}: {p.title[:60]}...")
            if len(papers) > 5:
                console.print(f"  ... and {len(papers) - 5} more")
        return

    stale = [p for p in papers if p.pdf_path and not p.pdf_path.exists()]
    if not stale:
        console.print("[green]No stale cache entries[/green]")
        return

    console.print(f"[yellow]{len(stale)} stale entries found:[/yellow]")
    for p in stale:
        console.print(f"  {p.doi or p.pmid}: {p.title[:60]}... (PDF missing)")
        if dry_run:
            continue
        if not yes:
            typer.confirm("  Remove?", abort=True)
        cache.remove(p.doi or "")
        console.print("  [green]✓[/] Removed")

    if dry_run:
        console.print("\nRun without --dry-run to remove them.")


@app.command()
def remove(
    identifier: str = typer.Argument(..., help="DOI / PMID to remove from cache"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a paper from cache."""
    cache = PaperCache()
    src = classify(identifier)
    key = src.cleaned if src.type == SourceType.doi else src.pmid
    paper = cache.get(key) if src.type == SourceType.doi else cache.get_by_pmid(src.pmid) if src.pmid else None

    if not paper:
        logger.error("Paper not found in cache")
        return

    if not yes:
        typer.confirm(f"Remove '{paper.title[:50]}'?", abort=True)

    cache.remove(paper.doi or "")
    if paper.pdf_path and paper.pdf_path.exists():
        paper.pdf_path.unlink()
    console.print(f"[green]✓[/] Removed: {paper.title[:50]}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
