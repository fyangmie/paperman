"""Offline migration and bounded-run regression checks."""

import json
import os
import shutil
import sys

from pypdf import PdfWriter
from paperman import bulk
from paperman.corpus.config import Settings
from paperman.corpus.network import Client


def test_corpus_network_follows_direct_config(tmp_path, monkeypatch):
    config = tmp_path / "config.ini"
    config.write_text("[settings]\nproxy_mode=direct\nproxy=http://unused:1\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", config)
    monkeypatch.setenv("HTTPS_PROXY", "http://environment:2")
    monkeypatch.delenv("PAPERMAN_CORPUS_PROXY", raising=False)
    client = Client(Settings())
    assert client.session.trust_env is False
    assert client.session.proxies == {}
    monkeypatch.setenv("PAPERMAN_CORPUS_PROXY", "http://corpus:3")
    overridden = Client(Settings())
    assert overridden.session.proxies["https"] == "http://corpus:3"
    assert overridden.session.trust_env is False


def test_resume_after_directory_move(tmp_path, monkeypatch):
    doi = "10.1234/move"
    old = tmp_path / "old"
    folder = old / bulk.key(doi)
    (folder / "pdfs").mkdir(parents=True)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(folder / "pdfs" / "article.pdf")
    bulk.save(
        folder / "result.json",
        {
            "doi": doi,
            "status": "downloaded",
            "download_source": "publisher",
            "pdf_files": [str(folder / "pdfs" / "article.pdf")],
        },
    )
    moved = tmp_path / "moved"
    shutil.move(old, moved)
    inputs = tmp_path / "dois.txt"
    inputs.write_text(doi + "\n")
    monkeypatch.setattr(sys, "argv", ["paperman-bulk", str(inputs), "--output", str(moved)])

    def no_download(*args, **kwargs):
        raise AssertionError("Existing readable PDF must not trigger network download")

    monkeypatch.setattr(bulk, "run_bounded", no_download)
    bulk.main()
    row = json.loads((moved / bulk.key(doi) / "result.json").read_text())
    assert row["pdf_files"] == ["pdfs/article.pdf"]
    assert row["status"] == "needs_review"
    totals = json.loads((moved / "summary.json").read_text())
    assert totals["saved_pdf_papers"] == 1
    assert totals["verified_pdf_papers"] == 0


def test_summary_does_not_promote_legacy_downloads(tmp_path):
    doi = "10.1234/legacy"
    folder = tmp_path / bulk.key(doi)
    folder.mkdir()
    bulk.save(folder / "result.json", {"status": "downloaded"})
    assert bulk.summary(tmp_path, [doi])["verified_pdf_papers"] == 0
    bulk.save(folder / "result.json", {"status": "no_pdf"})
    assert bulk.summary(tmp_path, [doi])["saved_pdf_papers"] == 0


def test_invalid_pdf_is_not_verified(tmp_path):
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / "fake.pdf").write_text("<html>login</html>")
    assert bulk.audit(tmp_path, "10.1234/fake")[0]["status"] == "invalid"


def test_timeout_stops_child(tmp_path):
    rc, expired = bulk.run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"], 0.1, tmp_path / "console.log", os.environ.copy()
    )
    assert expired
    assert rc is not None and rc != 0

def test_source_configuration_and_retries(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from paperman.downloaders.pipeline import DownloadPipeline
    from paperman.models.paper import Paper
    import pytest
    for names in (["bad"], ["pmc", "pmc"], ["arxiv_title", "pmc"]):
        with pytest.raises(ValueError):
            DownloadPipeline(names)
    monkeypatch.setenv("PAPERMAN_SOURCES", "publisher,pmc")
    monkeypatch.setenv("PAPERMAN_RETRIES", "2")
    pipeline = DownloadPipeline()
    assert [d.name for d in pipeline.downloaders] == ["publisher", "pmc"]
    assert not pipeline.title_fallback
    source = Mock()
    source.name = "publisher"
    source.iter_pdf_urls.side_effect = lambda paper: iter([])
    pipeline.downloaders = [source]
    monkeypatch.setattr("paperman.downloaders.pipeline.time.sleep", lambda seconds: None)
    assert pipeline.download(Paper(doi="10.1234/test"), tmp_path) is None
    assert source.iter_pdf_urls.call_count == 3


def test_interrupted_task_is_recorded(tmp_path, monkeypatch):
    import pytest
    inputs = tmp_path / "dois.txt"
    inputs.write_text("10.1234/interrupted")
    output = tmp_path / "task"
    monkeypatch.setattr(sys, "argv", ["paperman-bulk", str(inputs), "--output", str(output)])
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(bulk, "run_bounded", interrupt)
    with pytest.raises(KeyboardInterrupt):
        bulk.main()
    assert json.loads((output / "run.json").read_text())["state"] == "interrupted"
    assert json.loads((output / "summary.json").read_text())["status_counts"] == {"interrupted": 1}
