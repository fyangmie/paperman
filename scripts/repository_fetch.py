#!/usr/bin/env python3
"""Match existing DOIs to Europe PMC OA records and download original full-text XML."""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from paperman.paths import corpus_directory
from paperman.corpus.config import Settings, normalize_doi
from paperman.corpus.network import Client
from paperman.corpus.store import Store, atomic_write, json_bytes, now
from paperman.corpus.validation import validate
from paperman.corpus.report import report
from web_fetch import export_fulltexts
import hashlib

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches", type=int, default=4)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", "-o", type=Path, default=corpus_directory())
    args = parser.parse_args()
    if args.batches < 1 or args.limit < 1:
        parser.error("positive limits required")
    store = Store(args.output)
    client = Client(Settings(interval=3, retries=0, timeout=25))
    papers = {p["doi"]: json.loads(p["metadata"]) for p in store.papers(False)}
    ordered = sorted(papers, key=lambda doi: (
        not any("creativecommons.org/licenses/" in x.get("url", "") for x in papers[doi].get("licenses", [])),
        doi))
    run = store.run("repository_fetch", {"repository": "Europe PMC OA", "max_batches": args.batches,
                                        "download_limit": args.limit, "publisher_credentials": False})
    result = {"queried_dois": 0, "matches": 0, "success": 0, "failed": 0,
              "skipped": 0, "search_errors": 0}
    matches = {}
    try:
        for offset in range(0, min(len(ordered), args.batches * 25), 25):
            batch = ordered[offset:offset + 25]
            query = "OPEN_ACCESS:Y AND (" + " OR ".join('DOI:"' + doi + '"' for doi in batch) + ")"
            response = client.get(BASE + "/search", params={"query": query, "format": "json", "pageSize": 100})
            result["queried_dois"] += len(batch)
            if response.status != "success":
                result["search_errors"] += 1
                print(json.dumps({"search_status": response.status, "http": response.http_status}), flush=True)
                continue
            try:
                items = response.json()["resultList"]["result"]
                if not isinstance(items, list):
                    raise ValueError("Invalid search response")
                for item in items:
                    try:
                        doi = normalize_doi(item.get("doi", ""))
                    except ValueError:
                        continue
                    if doi in papers and item.get("pmcid") and item.get("isOpenAccess") == "Y":
                        matches[doi] = {"doi": doi, "pmcid": item["pmcid"],
                                        "publisher": papers[doi]["publisher"], "isOpenAccess": "Y"}
            except (ValueError, KeyError, TypeError):
                result["search_errors"] += 1
            print(json.dumps({"queried_dois": result["queried_dois"], "oa_repository_matches": len(matches)}), flush=True)
        result["matches"] = len(matches)
        atomic_write(store.root / "reports/oa-repository-matches.json",
                     json_bytes({"generated_at": now(), "repository": "Europe PMC OA", "matches": list(matches.values())}))
        # Test publishers beyond the already proven Springer HTML route first.
        for doi, match in sorted(matches.items(), key=lambda p: (p[1]["publisher"] == "springer_nature", p[0])):
            if store.valid_file(doi, "xml"):
                result["skipped"] += 1
                continue
            if result["success"] + result["failed"] >= args.limit:
                break
            pmcid = match["pmcid"]
            if not pmcid.startswith("PMC") or not pmcid[3:].isdigit():
                continue
            url = BASE + "/" + pmcid + "/fullTextXML"
            response = client.get(url)
            valid, detail = validate(response.body, "xml", doi, response.content_type) if response.status == "success" else (False, response.detail or response.status)
            status = "success" if valid else ("validation_failed" if response.status == "success" else response.status)
            store.attempt(doi, "xml", "europepmc:oa_xml", url, status,
                          response.http_status, detail, response.retries)
            if valid:
                path = store.directory(doi) / "article.xml"
                atomic_write(path, response.body)
                store.result(doi, "xml", "success", detail,
                             path=str(path.relative_to(store.root)),
                             sha256=hashlib.sha256(response.body).hexdigest(), size=len(response.body),
                             source_url=url, final_url=response.url, content_type=response.content_type,
                             acquired_at=now(), access_basis="repository_open_access")
            else:
                store.result(doi, "xml", status, detail)
            result["success" if valid else "failed"] += 1
            print(json.dumps({"doi": doi, "publisher": match["publisher"], "pmcid": pmcid,
                              "http": response.http_status, "status": status, "detail": detail}), flush=True)
            store.manifest()
        store.finish(run, result)
    finally:
        report(store)
        totals = export_fulltexts(store)
        client.session.close()
        store.close()
    print(json.dumps({"run": result, "matched_publishers": dict(Counter(m["publisher"] for m in matches.values())),
                      "corpus": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
