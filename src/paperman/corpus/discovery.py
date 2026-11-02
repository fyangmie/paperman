from __future__ import annotations

import hashlib
import json
import re
import math
from dataclasses import asdict
from pathlib import Path

from .config import PUBLISHERS, PREFIXES, Settings, normalize_doi, publisher_for
from .network import Client, safe_url
from .store import Store, now


def clean_text(text) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def parse_crossref(item: dict, settings: Settings) -> dict | None:
    try:
        doi = normalize_doi(item.get("DOI", ""))
    except ValueError:
        return None
    if item.get("type") != "journal-article":
        return None
    dates = item.get("published", item.get("issued", {})).get("date-parts", [[]])
    parts = dates[0] if dates else []
    if not parts:
        return None
    try:
        from datetime import date
        published = date(*([*parts, 1, 1][:3])).isoformat()
    except (ValueError, TypeError):
        return None
    if not settings.start_date <= published <= settings.end_date:
        return None
    publisher = publisher_for(doi, item.get("publisher", ""))
    if publisher not in PUBLISHERS:
        return None
    title = clean_text(" ".join(item.get("title", [])))
    abstract = clean_text(item.get("abstract", ""))
    haystack = (title + " " + abstract).lower()
    matched = [word for word in settings.keywords if word.lower() in haystack]
    if not matched:
        return None
    links = []
    for link in item.get("link", []):
        url = link.get("URL", "")
        if url.startswith("https://"):
            links.append({"url": safe_url(url), "content_type": link.get("content-type", ""),
                          "intended_application": link.get("intended-application", "")})
    licenses = [{"url": safe_url(v["URL"]), "start": v.get("start")}
                for v in item.get("license", []) if v.get("URL")]
    # Metadata JSON must not retain credentials embedded in URLs.
    raw = scrub(item)
    return {"doi": doi, "publisher": publisher, "publisher_name": item.get("publisher", ""),
            "title": title, "abstract": abstract, "abstract_missing": not bool(abstract),
            "journal": " ".join(item.get("container-title", [])), "year": parts[0],
            "published": published, "authors": item.get("author", []),
            "keywords_matched": matched, "links": links, "licenses": licenses,
            "landing_url": safe_url(item.get("resource", {}).get("primary", {}).get("URL") or
                                    item.get("URL") or f"https://doi.org/{doi}"),
            "metadata_source": "crossref", "discovered_at": now(), "raw_crossref": raw}


def scrub(value):
    from .network import SECRET_NAMES
    if isinstance(value, dict):
        return {k: "REDACTED" if k.lower() in SECRET_NAMES else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return safe_url(value)
    return value


def enrich(metadata: dict, client: Client) -> dict:
    import os
    key = os.environ.get("OPENALEX_API_KEY", "")
    response = client.get("https://api.openalex.org/works/https://doi.org/" + metadata["doi"],
                          params={"api_key": key} if key else None)
    metadata["openalex_status"] = response.status
    if response.status != "success":
        return metadata
    try:
        data = response.json()
        metadata["raw_openalex"] = scrub(data)
        if not metadata.get("abstract") and data.get("abstract_inverted_index"):
            positions = [(position, word) for word, places in data["abstract_inverted_index"].items() for position in places]
            metadata["abstract"] = " ".join(word for _, word in sorted(positions))
            metadata["abstract_missing"] = False
        for location in data.get("locations", []):
            if location.get("landing_page_url"):
                metadata.setdefault("openalex_locations", []).append({
                    "url": safe_url(location["landing_page_url"]),
                    "is_oa": bool(location.get("is_oa")), "license": location.get("license"),
                })
    except (ValueError, TypeError, KeyError):
        metadata["openalex_status"] = "invalid_metadata"
    return metadata


def fetch_doi(doi: str, settings: Settings, client: Client) -> tuple[dict | None, str]:
    from urllib.parse import quote
    response = client.get("https://api.crossref.org/works/" + quote(doi, safe=""))
    if response.status != "success":
        return None, response.status
    try:
        metadata = parse_crossref(response.json()["message"], settings)
    except (ValueError, KeyError, TypeError):
        return None, "invalid_metadata"
    if not metadata:
        return None, "outside_scope"
    if settings.openalex:
        metadata = enrich(metadata, client)
    return metadata, "success"


def queries(settings: Settings, publisher: str):
    first = int(settings.start_date[:4])
    last = int(settings.end_date[:4])
    windows = []
    for year in range(first, last + 1, 5):
        start = max(settings.start_date, f"{year:04d}-01-01")
        end = min(settings.end_date, f"{year + 4:04d}-12-31")
        windows.append((start, end))
    quota = math.ceil(settings.candidates_per_publisher / len(windows))
    for start, end in windows:
        for prefix in PREFIXES[publisher]:
            for keyword in settings.keywords:
                yield prefix, keyword, start, end, quota


def discover(store: Store, settings: Settings, client: Client, identifiers: Path | None = None) -> dict:
    run_id = store.run("discover", asdict(settings))
    errors, accepted = 0, 0
    if identifiers:
        seen = set()
        for line in identifiers.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                doi = normalize_doi(line)
            except ValueError:
                store.discovery_event("import", "invalid_doi", "Invalid input line")
                errors += 1
                continue
            if doi in seen:
                continue
            seen.add(doi)
            metadata, status = fetch_doi(doi, settings, client)
            store.discovery_event("doi:" + doi, status, "DOI metadata lookup")
            if metadata:
                store.put_paper(metadata)
                accepted += 1
            elif status != "outside_scope":
                errors += 1
    else:
        for publisher in PUBLISHERS:
            for prefix, keyword, window_start, window_end, quota in queries(settings, publisher):
                if store.count(publisher, window_start, window_end) >= quota:
                    continue
                params = {"filter": f"type:journal-article,from-pub-date:{window_start},until-pub-date:{window_end},prefix:{prefix}",
                          "query": keyword, "rows": min(settings.page_size, quota), "sort": "created", "order": "asc"}
                if settings.contact:
                    params["mailto"] = settings.contact
                key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
                checkpoint = store.db.execute("SELECT * FROM discovery WHERE query_key=?", (key,)).fetchone()
                if checkpoint and checkpoint["done"]:
                    continue
                cursor = checkpoint["cursor"] if checkpoint else "*"
                for _ in range(settings.max_pages):
                    response = client.get("https://api.crossref.org/works", params=dict(params, cursor=cursor))
                    if response.status != "success":
                        store.discovery_event(key, response.status, response.detail)
                        errors += 1
                        # A dead network should not trigger hundreds of equivalent requests.
                        if response.status == "network_error":
                            store.select(settings.per_publisher, settings.seed)
                            store.manifest()
                            result = {"accepted": accepted, "errors": errors, "selected": len(store.papers())}
                            store.finish(run_id, result)
                            return result
                        break
                    try:
                        message = response.json()["message"]
                        items = message["items"]
                        if not isinstance(items, list):
                            raise ValueError("Invalid items")
                    except (ValueError, KeyError, TypeError):
                        store.discovery_event(key, "invalid_metadata", "Invalid Crossref response")
                        errors += 1
                        break
                    for item in items:
                        metadata = parse_crossref(item, settings)
                        if metadata and metadata["publisher"] == publisher and window_start <= metadata["published"] <= window_end:
                            if settings.openalex:
                                metadata = enrich(metadata, client)
                            store.put_paper(metadata)
                            accepted += 1
                    next_cursor = message.get("next-cursor", "")
                    done = not items or len(items) < params["rows"] or not next_cursor or next_cursor == cursor
                    store.checkpoint(key, next_cursor or cursor, done)
                    store.discovery_event(key, "success", f"{len(items)} metadata records retrieved")
                    cursor = next_cursor
                    if done or store.count(publisher, window_start, window_end) >= quota:
                        break
    store.select(settings.per_publisher, settings.seed)
    store.manifest()
    result = {"accepted": accepted, "errors": errors, "selected": len(store.papers())}
    store.finish(run_id, result)
    return result
