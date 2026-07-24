from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from paperman.models.paper import Paper

CACHE_DIR = Path.home() / ".cache" / "paperman"


def _ensure_db():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DIR / "papers.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            doi TEXT PRIMARY KEY,
            pmid TEXT,
            pmcid TEXT,
            arxiv_id TEXT,
            data TEXT NOT NULL,
            pdf_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pmid ON papers(pmid)
    """)
    conn.commit()
    return conn


class PaperCache:
    def __init__(self):
        self.conn = _ensure_db()

    def get(self, doi: str) -> Optional[Paper]:
        cur = self.conn.execute("SELECT data FROM papers WHERE doi = ?", (doi,))
        row = cur.fetchone()
        if row:
            return Paper.model_validate_json(row[0])
        return None

    def get_by_pmid(self, pmid: str) -> Optional[Paper]:
        cur = self.conn.execute("SELECT data FROM papers WHERE pmid = ?", (pmid,))
        row = cur.fetchone()
        if row:
            return Paper.model_validate_json(row[0])
        return None

    def set(self, paper: Paper) -> None:
        if not paper.doi:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO papers (doi, pmid, pmcid, arxiv_id, data, pdf_path) VALUES (?, ?, ?, ?, ?, ?)",
            (
                paper.doi,
                paper.pmid,
                paper.pmcid,
                paper.arxiv_id,
                paper.model_dump_json(),
                str(paper.pdf_path) if paper.pdf_path else None,
            ),
        )
        self.conn.commit()

    def update_pdf_path(self, doi: str, path: Path) -> None:
        self.conn.execute("UPDATE papers SET pdf_path = ? WHERE doi = ?", (str(path), doi))
        # Also update the JSON blob so get() returns it
        cur = self.conn.execute("SELECT data FROM papers WHERE doi = ?", (doi,))
        row = cur.fetchone()
        if row:
            paper = Paper.model_validate_json(row[0])
            paper.pdf_path = path
            self.conn.execute("UPDATE papers SET data = ? WHERE doi = ?", (paper.model_dump_json(), doi))
        self.conn.commit()

    def list_all(self) -> list[Paper]:
        cur = self.conn.execute("SELECT data FROM papers ORDER BY created_at DESC")
        return [Paper.model_validate_json(row[0]) for row in cur.fetchall()]

    def search(self, query: str) -> list[Paper]:
        q = f"%{query}%"
        cur = self.conn.execute(
            "SELECT data FROM papers WHERE doi LIKE ? OR pmid LIKE ? OR data LIKE ? ORDER BY created_at DESC",
            (q, q, q),
        )
        papers = [Paper.model_validate_json(row[0]) for row in cur.fetchall()]
        query_lower = query.lower()
        return [
            p for p in papers
            if query_lower in p.title.lower()
            or query_lower in str(p.authors).lower()
            or query_lower in p.journal.lower()
        ]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()

    def remove(self, doi: str) -> None:
        self.conn.execute("DELETE FROM papers WHERE doi = ?", (doi,))
        self.conn.commit()
