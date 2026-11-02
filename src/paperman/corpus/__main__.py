"""Dependency-light entry point: python3 -m paperman.corpus (requires requests only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .discovery import discover
from .network import Client
from .pipeline import fetch, import_delivery
from .report import report
from .store import Store

from paperman.paths import corpus_directory
DEFAULT_OUTPUT = corpus_directory()


def main():
    parser = argparse.ArgumentParser(description="Paperman HTML/XML corpus acquisition")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("discover", "fetch", "report", "import-delivery"):
        command = commands.add_parser(name)
        command.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
        if name in {"discover", "fetch"}:
            command.add_argument("--config", type=Path)
        if name == "discover":
            command.add_argument("--identifiers", type=Path)
            command.add_argument("--per-publisher", type=int)
        if name == "fetch":
            command.add_argument("--formats", default="html,xml")
            command.add_argument("--resume", action="store_true")
        if name == "import-delivery":
            command.add_argument("doi")
            command.add_argument("file", type=Path)
            command.add_argument("--format", required=True)
            command.add_argument("--access-basis", required=True)
    args = parser.parse_args()
    store = Store(args.output)
    exit_code = 0
    try:
        config = getattr(args, "config", None)
        previous = store.db.execute("SELECT settings FROM runs WHERE kind='discover' ORDER BY id DESC LIMIT 1").fetchone()
        settings = Settings.load(config) if config or not previous else Settings(**json.loads(previous[0]))
        if args.command == "discover":
            if args.per_publisher is not None:
                settings.per_publisher = args.per_publisher
                settings.candidates_per_publisher = max(settings.candidates_per_publisher, args.per_publisher * 5)
                settings.__post_init__()
            result = discover(store, settings, Client(settings), args.identifiers)
            exit_code = int(bool(result["errors"]))
        elif args.command == "fetch":
            result = fetch(store, settings, Client(settings), tuple(s.strip() for s in args.formats.split(",")), args.resume)
            exit_code = int(bool(result["failed"]) or not result["papers"])
        elif args.command == "import-delivery":
            result = import_delivery(store, settings, {"doi": args.doi}, args.file, args.format, args.access_basis)
        else:
            result = {"reports": str(store.root / "reports")}
        report(store)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as exc:
        print("Corpus command failed: " + str(exc))
        exit_code = 1
    finally:
        store.close()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
