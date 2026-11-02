from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict

from .config import PUBLISHERS
from .store import Store, atomic_write, json_bytes, now

RETRYABLE = {"network_error", "server_error", "rate_limited", "stale_file", "http_error"}


def report(store: Store) -> dict:
    rows = store.papers()
    groups = {publisher: Counter() for publisher in PUBLISHERS}
    years = defaultdict(Counter)
    failures = Counter()
    retries = []
    review = []
    attempted_formats = set()
    for run in store.db.execute("SELECT settings FROM runs WHERE kind='fetch'"):
        attempted_formats.update(json.loads(run[0]).get("formats", []))
    if not attempted_formats:
        attempted_formats = {"html", "xml"}
    for row in rows:
        metadata = json.loads(row["metadata"])
        publisher = row["publisher"]
        counts = groups[publisher]
        counts["selected"] += 1
        known_oa = any(location.get("is_oa") for location in metadata.get("openalex_locations", []))
        counts["known_oa" if known_oa else "access_unknown"] += 1
        counts["abstract_missing"] += bool(metadata.get("abstract_missing", not metadata.get("abstract")))
        valid_formats = []
        for fmt in ("html", "xml"):
            artifact = store.artifact(row["doi"], fmt)
            status = artifact["status"] if artifact else "pending" if fmt in attempted_formats else "not_requested"
            if status == "success" and not store.valid_file(row["doi"], fmt):
                status = "stale_file"
            counts[fmt + ":" + status] += 1
            if status == "success":
                valid_formats.append(fmt)
                review.append({"doi": row["doi"], "publisher": publisher, "format": fmt,
                               "path": artifact["path"], "sha256": artifact["sha256"], "automatic_validation": artifact["detail"],
                               "body_checked": "", "identity_checked": "", "notes": ""})
            else:
                failures[status] += 1
                if status in RETRYABLE:
                    retries.append({"doi": row["doi"], "format": fmt, "reason": status})
        counts["any_fulltext"] += bool(valid_formats)
        counts["both_formats"] += len(valid_formats) == 2
        year = str(metadata.get("year", "unknown"))
        years[year]["selected"] += 1
        years[year]["any_fulltext"] += bool(valid_formats)
    latest = store.db.execute("SELECT settings FROM runs WHERE kind='discover' ORDER BY id DESC LIMIT 1").fetchone()
    target = json.loads(latest[0]).get("per_publisher", 20) if latest else 20
    attempts = store.db.execute("SELECT count(*),coalesce(sum(retries),0) FROM attempts").fetchone()
    successful = list(store.db.execute("SELECT doi,format,size,acquired_at FROM artifacts WHERE status='success'"))
    data = {
        "generated_at": now(), "selected": len(rows), "candidates": len(store.papers(selected=False)),
        "target_per_publisher": target,
        "publishers": {}, "years": {year: dict(counts) for year, counts in sorted(years.items())},
        "format_failures": dict(failures), "attempts": attempts[0], "http_retries": attempts[1],
        "stored_bytes": sum(row["size"] or 0 for row in successful if store.valid_file(row["doi"], row["format"])),
        "discovery_errors": [dict(row) for row in store.db.execute(
            "SELECT * FROM discovery_events WHERE status!='success' ORDER BY id")],
        "runs": [dict(row) for row in store.db.execute("SELECT * FROM runs ORDER BY id")],
        "manual_review": "pending; complete review.tsv before accepting pilot",
    }
    for publisher, counts in groups.items():
        n = counts["selected"]
        data["publishers"][publisher] = dict(counts, candidates=store.count(publisher),
            sample_gap=max(0, target - n),
            coverage={key: (counts[key] / n if n else None)
                      for key in ("html:success", "xml:success", "any_fulltext", "both_formats")})
    from datetime import datetime
    for run in data["runs"]:
        if run.get("finished_at"):
            run["elapsed_seconds"] = (datetime.fromisoformat(run["finished_at"]) -
                                      datetime.fromisoformat(run["created_at"])).total_seconds()
        else:
            run["elapsed_seconds"] = None
    data["any_fulltext"] = sum(c["any_fulltext"] for c in groups.values())
    data["both_formats"] = sum(c["both_formats"] for c in groups.values())
    root = store.root / "reports"
    atomic_write(root / "summary.json", json_bytes(data))
    lines = ["# Polymer corpus acquisition report", "", f"Generated: {data['generated_at']}", "",
             f"Candidates: {data['candidates']}; selected: {len(rows)}; "
             f"at least one full text: {data['any_fulltext']}; both formats: {data['both_formats']}.", "",
             "Coverage is measured against selected papers. Zero samples means unavailable evidence, not zero coverage.", "",
             "| Publisher | Selected | Gap | HTML | XML | Either | Both |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for publisher, counts in data["publishers"].items():
        lines.append(f"| {publisher} | {counts.get('selected', 0)} | {counts['sample_gap']} | "
                     f"{counts.get('html:success', 0)} | {counts.get('xml:success', 0)} | "
                     f"{counts.get('any_fulltext', 0)} | {counts.get('both_formats', 0)} |")
    lines += ["", "## Failure / pending states", ""]
    lines += [f"- {key}: {count}" for key, count in sorted(failures.items())] or ["- No format tasks registered."]
    lines += ["", f"Discovery errors: {len(data['discovery_errors'])}; attempts: {attempts[0]}; "
              f"HTTP retries: {attempts[1]}; stored bytes: {data['stored_bytes']}.", "",
              "## Acceptance", "", "- [ ] All five publishers reach their sample targets or gaps are explained.",
              "- [ ] Inspect successful files and complete review.tsv (body and DOI/title).",
              "- [ ] Confirm channel permissions and configure missing credentials.",
              "- [ ] Review discovery errors in summary.json; acquisition has no guaranteed coverage.",
              "", "Run timestamps and settings are retained in summary.json and corpus.sqlite.",
              "Subscription HTML/XML acquisition depends on configured, verified publisher channels."]
    atomic_write(root / "summary.md", ("\n".join(lines) + "\n").encode())
    atomic_write(root / "retry.jsonl", ("".join(json.dumps(row) + "\n" for row in retries)).encode())
    # Preserve human review when a report is regenerated; expose newly successful files too.
    review_path = root / "review.tsv"
    existing = {}
    if review_path.exists():
        with review_path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                existing[(row["doi"], row["format"], row.get("sha256", ""))] = row
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["doi", "publisher", "format", "path", "sha256", "automatic_validation",
                                           "body_checked", "identity_checked", "notes"], delimiter="\t")
    writer.writeheader()
    for row in review:
        old = existing.get((row["doi"], row["format"], row["sha256"]), {})
        for key in ("body_checked", "identity_checked", "notes"):
            row[key] = old.get(key, "")
        writer.writerow(row)
    atomic_write(review_path, out.getvalue().encode())
    store.manifest()
    return data
