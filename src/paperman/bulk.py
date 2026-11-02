"""Portable, bounded native PDF batches. Supported on POSIX (Linux/WSL)."""

import argparse, collections, csv, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
import yaml
from pypdf import PdfReader


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def key(doi):
    return hashlib.sha256(doi.encode()).hexdigest()


def audit(folder, doi):
    records = []
    for path in sorted((folder / "pdfs").glob("*.pdf")):
        row = {"path": str(path.relative_to(folder)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            reader = PdfReader(path)
            text = "".join(page.extract_text() or "" for page in reader.pages[:20])
            compact = lambda s: "".join(s.lower().split())
            row.update(pages=len(reader.pages), doi_match=compact(doi) in compact(text))
            row["status"] = ("verified" if row["doi_match"] else "needs_review") if len(reader.pages) > 0 else "invalid"
        except Exception as exc:
            row.update(status="invalid", error=type(exc).__name__)
        records.append(row)
    return records


def summary(root, dois):
    counts = collections.Counter()
    sources = collections.Counter()
    verified = 0
    for doi in dois:
        path = root / key(doi) / "result.json"
        if not path.exists():
            continue
        row = json.loads(path.read_text())
        counts[row["status"]] += 1
        if row["status"] == "downloaded" and any(a.get("status") == "verified" for a in row.get("audit", [])):
            verified += 1
        if row["status"] in ("downloaded", "needs_review"):
            sources[row.get("download_source") or "unknown"] += 1
    data = {
        "selected": len(dois),
        "processed": sum(counts.values()),
        "status_counts": dict(counts),
        "saved_pdf_papers": counts["downloaded"] + counts["needs_review"],
        "verified_pdf_papers": verified,
        "download_sources": dict(sources),
    }
    save(root / "summary.json", data)
    return data


def run_bounded(command, timeout, log, env):
    with log.open("w") as stream:
        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            return child.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            stop(child)
            return child.returncode, True
        except BaseException:
            stop(child)
            raise


def stop(child):
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()


def main():
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--report-only", action="store_true", help="Rebuild summary from latest per-DOI results")
    parser.add_argument("--sources", default="arxiv,pmc,scihub,publisher,arxiv_title",
                        help="Comma-separated ordered sources; arxiv_title, if included, must be last")
    parser.add_argument("--retries", type=int, default=1, help="Extra rounds before final title lookup")
    args = parser.parse_args()
    from paperman.downloaders.pipeline import DownloadPipeline
    try:
        DownloadPipeline(args.sources.split(","))
    except ValueError as exc:
        parser.error(str(exc))
    if args.retries < 0:
        parser.error("retries must be nonnegative")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    root = args.output.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    dois = list(dict.fromkeys(x.strip() for x in args.input.read_text().splitlines() if x.strip()))
    with (root / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another task is using this output directory")
        if args.report_only:
            print(json.dumps(summary(root, dois)))
            return
        save(
            root / "run.json", {"input_dois": dois, "timeout": args.timeout, "sources": args.sources.split(","), "retries": args.retries, "python": sys.version, "state": "running"}
        )
        summary(root, dois)
        for doi in dois:
            folder = root / key(doi)
            folder.mkdir(exist_ok=True)
            result = folder / "result.json"
            previous = json.loads(result.read_text()) if result.exists() else {}
            files = audit(folder, doi)
            if (
                previous.get("status") in ("downloaded", "needs_review")
                and files
                and all(x["status"] != "invalid" for x in files)
            ):
                previous.update(
                    pdf_files=[x["path"] for x in files],
                    audit=files,
                    status="downloaded" if any(x["status"] == "verified" for x in files) else "needs_review",
                )
                save(result, previous)
                summary(root, dois)
                print(
                    json.dumps({"doi": doi, "status": "skipped_existing", "validation": previous["status"]}), flush=True
                )
                continue
            attempt_dir = folder / "attempts" / str(time.time_ns())
            attempt_dir.mkdir(parents=True)
            inp = attempt_dir / "doi.txt"
            inp.write_text(doi + "\n")
            tsv = attempt_dir / "native_results.tsv"
            env = os.environ.copy()
            env["PAPERMAN_DIAGNOSTICS"] = str(attempt_dir / "requests.jsonl")
            env["PAPERMAN_CURRENT_DOI"] = doi
            env["PAPERMAN_STAGES"] = str(attempt_dir / "stages.jsonl")
            env["PAPERMAN_SOURCES"] = args.sources
            env["PAPERMAN_RETRIES"] = str(args.retries)
            started = time.monotonic()
            try:
                rc, expired = run_bounded(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "paperman",
                        "batch",
                        str(inp),
                        "--output",
                        str(folder / "pdfs"),
                        "--log",
                        str(tsv),
                    ],
                    args.timeout,
                    attempt_dir / "console.log",
                    env,
                )
            except KeyboardInterrupt:
                save(result, {"doi": doi, "status": "interrupted", "attempt": str(attempt_dir.relative_to(root))})
                save(root / "run.json", {"input_dois": dois, "state": "interrupted", "current_doi": doi})
                summary(root, dois)
                raise
            status = "timeout" if expired else "process_error" if rc else "no_pdf"
            source = None
            files = audit(folder, doi)
            if not expired and not rc and tsv.exists():
                with tsv.open() as stream:
                    rows = list(csv.DictReader(stream, delimiter="\t"))
                if rows and rows[0].get("pdf") == "yes":
                    status = (
                        "downloaded"
                        if any(x["status"] == "verified" for x in files)
                        else "needs_review"
                        if any(x["status"] == "needs_review" for x in files)
                        else "invalid_pdf"
                    )
                elif rows and rows[0].get("status") == "failure":
                    status = "metadata_failed"
            for pdf in (folder / "pdfs").glob("*.pdf"):
                meta = pdf.with_suffix(".yaml")
                if meta.exists():
                    source = (yaml.safe_load(meta.read_text()) or {}).get("sources", {}).get("pdf")
            stage_path = attempt_dir / "stages.jsonl"
            events = []
            if stage_path.exists():
                for line in stage_path.read_text().splitlines():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # A killed process may leave a partial final event.
            metadata = next((e for e in events if e.get("stage") == "metadata" and e.get("outcome") == "found"), {})
            last = events[-1] if events else {}
            row = {
                "article_publisher": metadata.get("publisher", ""),
                "article_journal": metadata.get("journal", ""),
                "metadata_source": metadata.get("source", ""),
                "failure_stage": None if status in ("downloaded", "needs_review") else last.get("stage", "startup"),
                "last_source": last.get("source"),
                "sources": args.sources.split(","),
                "retries": args.retries,
                "doi": doi,
                "status": status,
                "seconds": round(time.monotonic() - started, 2),
                "returncode": rc,
                "download_source": source,
                "pdf_files": [x["path"] for x in files],
                "audit": files,
                "attempt": str(attempt_dir.relative_to(root)),
            }
            save(result, row)
            with (root / "attempts.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            summary(root, dois)
            print(json.dumps(row), flush=True)
        save(root / "run.json", {"input_dois": dois, "timeout": args.timeout, "sources": args.sources.split(","), "retries": args.retries, "state": "completed"})
        summary(root, dois)


if __name__ == "__main__":
    main()
