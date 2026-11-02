from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import document_id, normalize_doi


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".partial-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "corpus.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS papers (
                doi TEXT PRIMARY KEY, publisher TEXT NOT NULL, metadata TEXT NOT NULL,
                selected INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                doi TEXT NOT NULL REFERENCES papers(doi), format TEXT NOT NULL,
                status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', path TEXT,
                sha256 TEXT, size INTEGER, source_url TEXT, final_url TEXT,
                content_type TEXT, acquired_at TEXT, access_basis TEXT,
                PRIMARY KEY (doi, format)
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY, doi TEXT NOT NULL REFERENCES papers(doi),
                format TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL,
                status TEXT NOT NULL, http_status INTEGER, detail TEXT NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery (
                query_key TEXT PRIMARY KEY, cursor TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery_events (
                id INTEGER PRIMARY KEY, query_key TEXT NOT NULL, status TEXT NOT NULL,
                detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, settings TEXT NOT NULL,
                created_at TEXT NOT NULL, finished_at TEXT, summary TEXT
            );
        """)

        # Additive migration for corpora created by an earlier version of this feature.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(runs)")}
        for name in ("finished_at", "summary"):
            if name not in columns:
                self.db.execute(f"ALTER TABLE runs ADD COLUMN {name} TEXT")
        self.db.commit()

    def close(self):
        self.db.close()

    def run(self, kind: str, settings: dict):
        cursor = self.db.execute("INSERT INTO runs(kind,settings,created_at) VALUES(?,?,?)",
                        (kind, json.dumps(settings, ensure_ascii=False), now()))
        self.db.commit()
        return cursor.lastrowid

    def finish(self, run_id: int, summary: dict):
        self.db.execute("UPDATE runs SET finished_at=?,summary=? WHERE id=?",
                        (now(), json.dumps(summary), run_id))
        self.db.commit()

    def put_paper(self, metadata: dict):
        doi = normalize_doi(metadata["doi"])
        metadata = dict(metadata, doi=doi)
        self.db.execute("""INSERT INTO papers(doi,publisher,metadata,created_at) VALUES(?,?,?,?)
            ON CONFLICT(doi) DO UPDATE SET publisher=excluded.publisher,metadata=excluded.metadata""",
                        (doi, metadata["publisher"], json.dumps(metadata, ensure_ascii=False), now()))
        self.db.commit()
        atomic_write(self.directory(doi) / "metadata.json", json_bytes(metadata))

    def directory(self, doi: str) -> Path:
        return self.root / "documents" / document_id(doi)

    def papers(self, selected: bool = True):
        query = "SELECT * FROM papers" + (" WHERE selected=1" if selected else "") + " ORDER BY doi"
        return [dict(row) for row in self.db.execute(query)]

    def count(self, publisher: str, start: str | None = None, end: str | None = None) -> int:
        if start and end:
            return self.db.execute("""SELECT count(*) FROM papers WHERE publisher=?
                AND json_extract(metadata,'$.published') BETWEEN ? AND ?""", (publisher, start, end)).fetchone()[0]
        return self.db.execute("SELECT count(*) FROM papers WHERE publisher=?", (publisher,)).fetchone()[0]

    def checkpoint(self, key: str, cursor: str, done: bool):
        self.db.execute("INSERT OR REPLACE INTO discovery VALUES(?,?,?,?)", (key, cursor, done, now()))
        self.db.commit()

    def discovery_event(self, key: str, status: str, detail: str):
        self.db.execute("INSERT INTO discovery_events(query_key,status,detail,created_at) VALUES(?,?,?,?)",
                        (key, status, detail, now()))
        self.db.commit()

    def select(self, per_publisher: int, seed: int):
        from .config import PUBLISHERS
        # Hash ranking makes samples deterministic and the larger pilot a superset.
        self.db.execute("UPDATE papers SET selected=0")
        for publisher in PUBLISHERS:
            rows = list(self.db.execute("SELECT doi FROM papers WHERE publisher=?", (publisher,)))
            # Round-robin year windows and known OA/unknown access, with stable ordering inside strata.
            from collections import defaultdict
            strata = defaultdict(list)
            for row in rows:
                metadata = json.loads(self.db.execute("SELECT metadata FROM papers WHERE doi=?", (row["doi"],)).fetchone()[0])
                year_bin = ((metadata.get("year") or 2000) // 5) * 5
                oa = any(v.get("is_oa") for v in metadata.get("openalex_locations", []))
                strata[(year_bin, oa)].append(row)
            for bucket in strata.values():
                bucket.sort(key=lambda row: hashlib.sha256(f"{seed}:{row['doi']}".encode()).hexdigest())
            rows = []
            for position in range(max((len(bucket) for bucket in strata.values()), default=0)):
                for key in sorted(strata):
                    if position < len(strata[key]):
                        rows.append(strata[key][position])
            self.db.executemany("UPDATE papers SET selected=1 WHERE doi=?",
                                [(row["doi"],) for row in rows[:per_publisher]])
        self.db.commit()

    def artifact(self, doi: str, fmt: str):
        row = self.db.execute("SELECT * FROM artifacts WHERE doi=? AND format=?", (doi, fmt)).fetchone()
        return dict(row) if row else None

    def valid_file(self, doi: str, fmt: str) -> bool:
        record = self.artifact(doi, fmt)
        if not record or record["status"] != "success" or not record["path"]:
            return False
        path = self.root / record["path"]
        if not path.is_file():
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]

    def attempt(self, doi, fmt, source, url, status, http_status=None, detail="", retries=0):
        self.db.execute("""INSERT INTO attempts
            (doi,format,source,url,status,http_status,detail,retries,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (doi, fmt, source, url, status, http_status, detail, retries, now()))
        self.db.commit()

    def result(self, doi: str, fmt: str, status: str, detail: str = "", **values):
        fields = ["doi", "format", "status", "detail", *values]
        placeholders = ",".join("?" for _ in fields)
        self.db.execute(f"INSERT OR REPLACE INTO artifacts ({','.join(fields)}) VALUES ({placeholders})",
                        [doi, fmt, status, detail, *values.values()])
        self.db.commit()

    def manifest(self):
        lines = []
        for row in self.papers(selected=False):
            record = json.loads(row["metadata"])
            record["selected"] = bool(row["selected"])
            record["artifacts"] = [dict(a) for a in self.db.execute(
                "SELECT * FROM artifacts WHERE doi=? ORDER BY format", (row["doi"],))]
            lines.append(json.dumps(record, ensure_ascii=False))
        atomic_write(self.root / "manifest.jsonl", ("\n".join(lines) + ("\n" if lines else "")).encode())
