#!/usr/bin/env python3
"""Fetch publisher HTML from existing corpus metadata without publisher APIs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

from paperman.paths import corpus_directory

from paperman.corpus.adapters import ADAPTERS
from paperman.corpus.config import Settings
from paperman.corpus.network import Client
from paperman.corpus.report import report
from paperman.corpus.store import Store, atomic_write, json_bytes, now
from paperman.corpus.validation import validate


def export_fulltexts(store):
    records = []
    for row in store.db.execute(
            "SELECT a.*,p.publisher,p.selected,p.metadata FROM artifacts a "
            "JOIN papers p ON p.doi=a.doi WHERE a.status='success' ORDER BY a.doi,a.format"):
        if not store.valid_file(row["doi"], row["format"]):
            continue
        record = dict(row)
        record["title"] = json.loads(record.pop("metadata"))["title"]
        record["selected"] = bool(record["selected"])
        records.append(record)
    atomic_write(store.root / "reports/fulltext-index.jsonl",
                 ("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)).encode())
    extra = [r for r in records if not r["selected"]]
    totals = {"generated_at": now(), "fulltext_files": len(records),
              "html": sum(r["format"] == "html" for r in records),
              "xml": sum(r["format"] == "xml" for r in records),
              "pilot_fulltext_papers": len({r["doi"] for r in records if r["selected"]}),
              "supplemental_files": len(extra), "index": "reports/fulltext-index.jsonl"}
    atomic_write(store.root / "reports/fulltext-totals.json", json_bytes(totals))
    path = store.root / "reports/supplemental-review.tsv"
    existing = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as stream:
            existing = {(r["doi"], r["format"], r["sha256"]): r for r in csv.DictReader(stream, delimiter="\t")}
    fields = ["doi", "publisher", "format", "path", "sha256", "automatic_validation",
              "body_checked", "identity_checked", "notes"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for record in extra:
        row = {key: record[key] for key in fields[:5]}
        previous = existing.get((record["doi"], record["format"], record["sha256"]), {})
        row["automatic_validation"] = record["detail"]
        for key in fields[6:]:
            row[key] = previous.get(key, "")
        writer.writerow(row)
    atomic_write(path, output.getvalue().encode())
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publisher", choices=sorted(ADAPTERS), default="springer_nature")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--retry-previews", action="store_true",
                        help="Retry rejected subscription previews after access changes")
    parser.add_argument("--output", "-o", type=Path, default=corpus_directory())
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    store = Store(args.output)
    settings = Settings.load(store.root / "config.toml")
    # This bounded channel trial records failures instead of repeatedly retrying them.
    settings.retries = 0
    settings.timeout = 25
    client = Client(settings)
    if args.direct:
        client.session.trust_env = False
        client.session.proxies.clear()
    run_id = store.run("web_fetch", {"publisher": args.publisher, "limit": args.limit,
                                    "publisher_api": False, "direct": args.direct})
    result = {"eligible": 0, "attempted": 0, "success": 0, "failed": 0, "skipped": 0, "preview_skipped": 0}
    papers = [json.loads(r["metadata"]) for r in store.papers(False) if r["publisher"] == args.publisher]
    papers.sort(key=lambda p: (p.get("published", ""), p["doi"]), reverse=True)
    try:
        for paper in papers:
            candidates, _ = ADAPTERS[args.publisher].candidates(paper, "html", settings)
            # Use only publisher-deposited HTML links or CC-licensed landing pages.
            # Do not invoke article APIs, configured credential channels, or PDF fallbacks.
            candidates = [c for c in candidates if c.source in {
                args.publisher + ":crossref", args.publisher + ":oa_landing"}]
            candidates = list({c.url: c for c in candidates}.values())
            if not candidates:
                continue
            result["eligible"] += 1
            doi = paper["doi"]
            if store.valid_file(doi, "html"):
                result["skipped"] += 1
                continue
            previous = store.artifact(doi, "html")
            if (not args.retry_previews and previous
                    and previous["status"] == "validation_failed"
                    and previous["detail"].startswith("Subscription preview;")):
                result["preview_skipped"] += 1
                continue
            if result["attempted"] >= args.limit:
                continue
            result["attempted"] += 1
            success = False
            for candidate in candidates:
                response = client.get(candidate.url, publisher=args.publisher)
                valid, detail = validate(response.body, "html", doi, response.content_type) if response.status == "success" else (False, response.detail or response.status)
                status = "success" if valid else ("validation_failed" if response.status == "success" else response.status)
                store.attempt(doi, "html", candidate.source, candidate.url, status,
                              response.http_status, detail, response.retries)
                print(json.dumps({"number": result["attempted"], "doi": doi,
                                  "http": response.http_status, "status": status,
                                  "detail": detail}, ensure_ascii=False), flush=True)
                if valid:
                    path = store.directory(doi) / "article.html"
                    atomic_write(path, response.body)
                    store.result(doi, "html", "success", detail,
                                 path=str(path.relative_to(store.root)),
                                 sha256=hashlib.sha256(response.body).hexdigest(), size=len(response.body),
                                 source_url=candidate.url, final_url=response.url,
                                 content_type=response.content_type, acquired_at=now(),
                                 access_basis=candidate.access_basis)
                    success = True
                    break
            if not success:
                store.result(doi, "html", status, detail)
            result["success" if success else "failed"] += 1
            store.manifest()
        store.finish(run_id, result)
    finally:
        report(store)
        totals = export_fulltexts(store)
        client.session.close()
        store.close()
    print(json.dumps({"run": result, "corpus": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
