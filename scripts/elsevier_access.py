#!/usr/bin/env python3
"""Configure a local Elsevier key and verify FULL XML access without logging secrets."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from paperman.paths import corpus_directory
KEY_FILE = Path.home() / ".config" / "paperman" / "elsevier-credentials.json"
OUTPUT = corpus_directory()


def configure():
    key = input("Elsevier API Key (visible input): ").strip()
    if not key:
        raise ValueError("Empty key; nothing saved")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".elsevier-", dir=KEY_FILE.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({"api_key": key}, stream)
        os.replace(temporary, KEY_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Key saved locally with owner-only file permissions. Key value is not printed.")


def credentials():
    data = {}
    if KEY_FILE.exists():
        if KEY_FILE.stat().st_mode & 0o077:
            raise ValueError("Credential file permissions must be 600")
        data = json.loads(KEY_FILE.read_text())
    key = os.environ.get("ELSEVIER_API_KEY") or data.get("api_key", "")
    token = os.environ.get("ELSEVIER_INSTTOKEN") or data.get("insttoken", "")
    if not key:
        raise ValueError("No key configured. Run this script with configure first.")
    return key, token


def client_for(settings, route):
    from paperman.corpus.network import Client
    client = Client(settings)
    if route == "direct":
        client.session.trust_env = False
        client.session.proxies.clear()
    return client


def probe():
    import sqlite3
    from paperman.corpus.config import Settings
    from paperman.corpus.store import atomic_write, json_bytes, now
    from paperman.corpus.validation import validate

    key, token = credentials()
    headers = {"X-ELS-APIKey": key, "Accept": "text/xml"}
    if token:
        headers["X-ELS-Insttoken"] = token
    db = sqlite3.connect(f"file:{OUTPUT / 'corpus.sqlite'}?mode=ro", uri=True)
    examples = {}
    for metadata, in db.execute("SELECT metadata FROM papers WHERE publisher='elsevier' ORDER BY selected DESC,doi"):
        paper = json.loads(metadata)
        if not paper["doi"].startswith("10.1016/"):
            continue
        kind = "cc_licensed" if any("creativecommons.org/licenses/" in x.get("url", "") for x in paper.get("licenses", [])) else "access_unknown"
        examples.setdefault(kind, paper["doi"])
        if len(examples) == 2:
            break
    db.close()
    if not examples:
        raise ValueError("No Elsevier DOI candidates available")
    settings = Settings(timeout=20, retries=0, interval=10)
    results = []
    # Share limiter state between routes to avoid doubling request rate.
    last = {}
    for route in ("direct", "configured_proxy"):
        client = client_for(settings, route)
        client.last = last
        try:
            for kind, doi in examples.items():
                response = client.get(
                    "https://api.elsevier.com/content/article/doi/" + doi,
                    params={"view": "FULL"}, headers=headers, publisher="elsevier")
                valid, detail = validate(response.body, "xml", doi, response.content_type) if response.status == "success" else (False, response.detail or response.status)
                error_code = ""
                try:
                    payload = response.json()
                    error = payload.get("error-response", {})
                    error_code = error.get("error-code", "") if isinstance(error, dict) else ""
                except (ValueError, AttributeError):
                    pass
                row = {"route": route, "doi": doi, "sample_kind": kind,
                       "http_status": response.http_status, "request_status": response.status,
                       "fulltext_valid": valid, "detail": detail, "api_error_code": error_code}
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            client.session.close()
    data = {"checked_at": now(), "school": "Shanghai University", "vpn": "OpenVPN",
            "results": results,
            "note": "Route means process proxy use; direct does not prove host VPN routing or institutional IP recognition."}
    path = OUTPUT / "reports" / "elsevier-access-probe.json"
    # Defense in depth: never serialize credentials into a report.
    serialized = json_bytes(data)
    if key.encode() in serialized or (token and token.encode() in serialized):
        raise ValueError("Report unexpectedly contains a credential; not saved")
    atomic_write(path, serialized)
    print("Report saved:", path)


def fetch(route):
    from paperman.corpus.config import Settings
    from paperman.corpus.pipeline import fetch as run_fetch
    from paperman.corpus.report import report
    from paperman.corpus.store import Store
    key, token = credentials()
    os.environ["ELSEVIER_API_KEY"] = key
    if token:
        os.environ["ELSEVIER_INSTTOKEN"] = token
    settings = Settings.load(OUTPUT / "config.toml")
    store = Store(OUTPUT)
    client = client_for(settings, route)
    try:
        result = run_fetch(store, settings, client, ("html", "xml"), resume=True)
        report(store)
        print(json.dumps(result))
    finally:
        client.session.close()
        store.close()


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure")
    commands.add_parser("probe")
    download = commands.add_parser("fetch")
    download.add_argument("--route", choices=("direct", "configured_proxy"), required=True)
    parser.add_argument("--output", "-o", type=Path, default=corpus_directory())
    args = parser.parse_args()
    OUTPUT = args.output
    if args.command == "configure":
        configure()
    elif args.command == "probe":
        probe()
    else:
        fetch(args.route)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyboardInterrupt) as exc:
        print("Configuration/probe stopped:", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
