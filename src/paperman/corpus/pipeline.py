from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .adapters import ADAPTERS, Candidate
from .config import Settings, normalize_doi
from .network import Client, safe_url
from .store import Store, atomic_write, now
from .validation import validate

ERROR_PRIORITY = {"network_error": 10, "server_error": 9, "rate_limited": 8,
                  "permission_denied": 7, "validation_failed": 6,
                  "missing_credentials": 5, "channel_unverified": 4,
                  "format_unavailable": 3, "not_found": 2}


def fetch(store: Store, settings: Settings, client: Client, formats=("html", "xml"), resume=False) -> dict:
    if not formats or set(formats) - {"html", "xml"}:
        raise ValueError("formats must contain html and/or xml")
    formats = tuple(dict.fromkeys(formats))
    run_id = store.run("fetch", {"settings": asdict(settings), "formats": formats, "resume": resume})
    summary = {"success": 0, "failed": 0, "skipped": 0, "papers": len(store.papers())}
    try:
        for row in store.papers():
            paper = json.loads(row["metadata"])
            doi = paper["doi"]
            adapter = ADAPTERS.get(row["publisher"])
            if not adapter:
                continue
            for fmt in formats:
                if resume and store.valid_file(doi, fmt):
                    summary["skipped"] += 1
                    continue
                # Preserve a previously verified artifact if a forced refresh fails.
                previous_valid = store.valid_file(doi, fmt)
                candidates, reason = adapter.candidates(paper, fmt, settings)
                if fmt == "html":
                    for location in paper.get("openalex_locations", []):
                        if location.get("is_oa") and location["url"].startswith("https://"):
                            candidates.append(Candidate(location["url"], "openalex:oa", "open_access"))
                unique = set()
                failures = [reason] if reason else []
                success = False
                for candidate in candidates:
                    if candidate.url in unique:
                        continue
                    unique.add(candidate.url)
                    response = client.get(candidate.url, headers=candidate.headers, publisher=row["publisher"])
                    status, detail = response.status, response.detail
                    if status == "success":
                        valid, detail = validate(response.body, fmt, doi, response.content_type)
                        if not valid:
                            status = "validation_failed"
                    store.attempt(doi, fmt, candidate.source, safe_url(candidate.url), status,
                                  response.http_status, detail, response.retries)
                    if status != "success":
                        failures.append(status)
                        continue
                    path = store.directory(doi) / ("article." + fmt)
                    atomic_write(path, response.body)
                    store.result(doi, fmt, "success", detail,
                                 path=str(path.relative_to(store.root)),
                                 sha256=hashlib.sha256(response.body).hexdigest(), size=len(response.body),
                                 source_url=safe_url(candidate.url), final_url=response.url,
                                 content_type=response.content_type, acquired_at=now(), access_basis=candidate.access_basis)
                    summary["success"] += 1
                    success = True
                    break
                if not success:
                    status = max(failures or ["format_unavailable"], key=lambda s: ERROR_PRIORITY.get(s, 1))
                    detail = "No validated full text; consult attempts and publisher configuration"
                    if not candidates:
                        store.attempt(doi, fmt, adapter.name, "", status, detail=detail)
                    if not previous_valid:
                        store.result(doi, fmt, status, detail)
                    summary["failed"] += 1
                # Keep an interruption-reviewable manifest after each format.
                store.manifest()
    finally:
        store.manifest()
    store.finish(run_id, summary)
    return summary


def import_delivery(store: Store, settings: Settings, metadata: dict, path, fmt: str,
                    access_basis: str) -> dict:
    """Register publisher-delivered full text after validating its identity and format."""
    if fmt not in {"html", "xml"} or not access_basis.strip():
        raise ValueError("Explicit html/xml format and access_basis required")
    doi = normalize_doi(metadata["doi"])
    paper = store.db.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone()
    if not paper:
        raise ValueError("Discover/register DOI metadata before importing delivery")
    if path.stat().st_size > settings.max_bytes:
        raise ValueError("Response exceeds max_bytes")
    body = path.read_bytes()
    valid, detail = validate(body, fmt, doi)
    store.attempt(doi, fmt, "publisher_delivery", "", "success" if valid else "validation_failed", detail=detail)
    if not valid:
        raise ValueError(detail)
    dest = store.directory(doi) / ("article." + fmt)
    atomic_write(dest, body)
    store.result(doi, fmt, "success", detail, path=str(dest.relative_to(store.root)),
                 sha256=hashlib.sha256(body).hexdigest(), size=len(body), source_url="publisher_delivery",
                 final_url="", content_type="", acquired_at=now(), access_basis=access_basis)
    store.manifest()
    return {"doi": doi, "format": fmt, "path": str(dest)}
