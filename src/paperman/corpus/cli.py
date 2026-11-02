from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .config import Settings
from .discovery import discover as run_discover
from .network import Client
from .pipeline import fetch as run_fetch, import_delivery
from .report import report as run_report
from .store import Store

# User-owned data location; explicit --output preserves existing corpus paths.
from paperman.paths import corpus_directory
DEFAULT_OUTPUT = corpus_directory()
app = typer.Typer(help="Discover, acquire and audit HTML/XML full-text corpora.", no_args_is_help=True)


def settings_for(config: Optional[Path], store: Store) -> Settings:
    if config:
        return Settings.load(config)
    row = store.db.execute("SELECT settings FROM runs WHERE kind='discover' ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        data = json.loads(row[0])
        data["keywords"] = tuple(data["keywords"])
        return Settings(**data)
    return Settings()


@app.command()
def discover(
    config: Optional[Path] = typer.Option(None, "--config", help="Corpus TOML settings"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o", help="Separate corpus directory"),
    identifiers: Optional[Path] = typer.Option(None, "--identifiers", help="Optional DOI list, one per line"),
    per_publisher: Optional[int] = typer.Option(None, "--per-publisher", min=1, help="20 for 100; 200 for 1000"),
):
    """Discover scoped journal articles and select a deterministic pilot."""
    store = Store(output)
    try:
        settings = settings_for(config, store)
        if per_publisher is not None:
            settings.per_publisher = per_publisher
            settings.candidates_per_publisher = max(settings.candidates_per_publisher, per_publisher * 5)
            settings.__post_init__()
        result = run_discover(store, settings, Client(settings), identifiers)
        run_report(store)
        typer.echo(json.dumps(result, ensure_ascii=False))
        if result["errors"]:
            raise typer.Exit(1)
    except (ValueError, OSError, TypeError) as exc:
        typer.echo(f"Discovery failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()


@app.command()
def fetch(
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o"),
    config: Optional[Path] = typer.Option(None, "--config"),
    formats: str = typer.Option("html,xml", "--formats"),
    resume: bool = typer.Option(False, "--resume"),
):
    """Attempt each requested format independently, preserving original bytes."""
    store = Store(output)
    try:
        settings = settings_for(config, store)
        result = run_fetch(store, settings, Client(settings), tuple(s.strip() for s in formats.split(",")), resume)
        run_report(store)
        typer.echo(json.dumps(result, ensure_ascii=False))
        if result["failed"] or not result["papers"]:
            raise typer.Exit(1)
    except (ValueError, OSError, TypeError) as exc:
        typer.echo(f"Fetch failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()


@app.command()
def report(output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o")):
    """Audit saved files and export coverage, retry and manual-review reports."""
    store = Store(output)
    try:
        data = run_report(store)
        typer.echo(f"{data['selected']} selected; {data['any_fulltext']} with full text; "
                   f"{data['both_formats']} with both formats. Reports: {store.root / 'reports'}")
    finally:
        store.close()


@app.command("import-delivery")
def delivery(
    doi: str = typer.Argument(...),
    file: Path = typer.Argument(..., exists=True, dir_okay=False),
    fmt: str = typer.Option(..., "--format"),
    access_basis: str = typer.Option(..., "--access-basis", help="Publisher delivery / agreement reference"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o"),
):
    """Validate and register a publisher-delivered HTML/XML file for a known DOI."""
    store = Store(output)
    try:
        result = import_delivery(store, settings_for(None, store), {"doi": doi}, file, fmt, access_basis)
        run_report(store)
        typer.echo(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        typer.echo(f"Import failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()
