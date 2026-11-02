"""Offline corpus acceptance tests; also runnable without pytest via unittest."""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from paperman.corpus.adapters import ADAPTERS
from paperman.corpus.config import Settings, normalize_doi
from paperman.corpus.discovery import discover, parse_crossref
from paperman.corpus.network import Client, Response, safe_url
from paperman.corpus.pipeline import fetch, import_delivery
from paperman.corpus.report import report
from paperman.corpus.store import Store
from paperman.corpus.validation import validate

DOI = "10.1021/test.1"
TEXT = "The polymer samples show a measured glass transition temperature and tensile strength. " * 8
XML = (f'<article><front><article-id pub-id-type="doi">{DOI}</article-id></front>'
       f'<body><sec><title>Results</title><p>{TEXT}</p></sec></body></article>').encode()
HTML = (f'<html><head><meta name="citation_doi" content="{DOI}"></head>'
        f'<body><div class="article-body"><p>{TEXT}</p><p>{TEXT}</p></div></body></html>').encode()


def item(doi=DOI, **kwargs):
    data = {"DOI": doi, "type": "journal-article", "published": {"date-parts": [[2020, 4]]},
            "title": ["A polymer study"], "abstract": "<p>Complete abstract of the study.</p>",
            "publisher": "American Chemical Society", "container-title": ["Polymer Journal"],
            "URL": "https://pubs.acs.org/doi/" + doi, "author": [{"family": "Researcher"}]}
    data.update(kwargs)
    return data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected network request: " + url)
        return self.responses.pop(0)


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)
        self.settings = Settings(interval=0, retries=0)
        self.paper = parse_crossref(item(), self.settings)
        self.store.put_paper(self.paper)
        self.store.select(20, 42)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def channels(self):
        return Settings(interval=0, retries=0, publishers={"acs": {
            "html_url": "https://pubs.acs.org/doi/full/{doi}",
            "xml_url": "https://pubs.acs.org/doi/xml/{doi}"}})

    def test_scope_and_metadata(self):
        self.assertEqual(self.paper["published"], "2020-04-01")
        self.assertEqual(self.paper["abstract"], "Complete abstract of the study.")
        self.assertIsNone(parse_crossref(item(type="book-chapter"), self.settings))
        self.assertIsNone(parse_crossref(item(published={"date-parts": [[1999]]}), self.settings))
        self.assertIsNone(parse_crossref(item(title=["Unrelated"], abstract=""), self.settings))
        self.assertIsNone(parse_crossref(item(published={"date-parts": [[2020, 99]]}), self.settings))

    def test_normalize_and_deduplicate(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1021/TEST.1"), DOI)
        self.store.put_paper(dict(self.paper, doi="10.1021/TEST.1"))
        self.assertEqual(len(self.store.papers(False)), 1)
        self.assertEqual(len(list((self.root / "documents").iterdir())), 1)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            Settings(per_publisher=201)
        with self.assertRaises(ValueError):
            Settings(publishers={"acs": {"xml_url": "http://insecure/{doi}"}})
        with self.assertRaises(ValueError):
            normalize_doi("not a DOI")

    def test_all_five_adapters(self):
        self.assertEqual(set(ADAPTERS), {"acs", "rsc", "wiley", "springer_nature", "elsevier"})
        for publisher in ADAPTERS:
            with self.subTest(publisher=publisher):
                candidates, reason = ADAPTERS[publisher].candidates(self.paper, "html", self.settings)
                self.assertFalse(candidates)
                self.assertTrue(reason)

    def test_configured_rsc_and_wiley_channels(self):
        for publisher, domain in [("rsc", "pubs.rsc.org"), ("wiley", "onlinelibrary.wiley.com")]:
            settings = Settings(publishers={publisher: {"xml_url": f"https://{domain}/xml/{{doi}}"}})
            candidates, _ = ADAPTERS[publisher].candidates(self.paper, "xml", settings)
            self.assertEqual(candidates[0].url, f"https://{domain}/xml/{DOI}")

    def test_elsevier_full_view_and_secret_headers(self):
        with patch.dict(os.environ, {"ELSEVIER_API_KEY": "hidden-value"}):
            candidates, _ = ADAPTERS["elsevier"].candidates(self.paper, "xml", self.settings)
        self.assertIn("view=FULL", candidates[0].url)
        self.assertEqual(candidates[0].headers["X-ELS-APIKey"], "hidden-value")
        self.assertNotIn("hidden-value", repr(candidates[0]))

    def test_springer_oa_api(self):
        with patch.dict(os.environ, {"SPRINGER_NATURE_API_KEY": "secret-value"}):
            candidates, _ = ADAPTERS["springer_nature"].candidates(self.paper, "xml", self.settings)
        self.assertIn("openaccess/jats", candidates[-1].url)
        self.assertNotIn("secret-value", safe_url(candidates[-1].url))

    def test_deposited_links_are_format_and_domain_specific(self):
        paper = dict(self.paper, links=[{"url": "https://pubs.acs.org/full.xml", "content_type": "application/xml"},
                                       {"url": "https://other.example/full.xml", "content_type": "application/xml"}])
        candidates, _ = ADAPTERS["acs"].candidates(paper, "xml", self.settings)
        self.assertEqual(len(candidates), 1)
        html, _ = ADAPTERS["acs"].candidates(paper, "html", self.settings)
        self.assertEqual(html, [])

    def test_cc_landing_fetch_and_access_boundaries(self):
        paper = dict(self.paper, licenses=[{"url": "https://creativecommons.org/licenses/by/4.0/"}])
        self.store.put_paper(paper)
        result = fetch(self.store, self.settings, FakeClient([Response("success", body=HTML)]), ("html",))
        self.assertEqual(result["success"], 1)
        self.assertTrue(self.store.valid_file(doi=self.paper["doi"], fmt="html"))
        for changes in [
            {"landing_url": "https://other.example/article"},
            {"licenses": [{"url": "https://example.org/creativecommons.org/licenses/by/4.0/"}]},
            {"licenses": [{"url": "https://creativecommons.org/licenses/by/4.0/",
                           "start": {"date-time": "2999-01-01T00:00:00Z"}}]},
        ]:
            candidates, _ = ADAPTERS["acs"].candidates(dict(paper, **changes), "html", self.settings)
            self.assertEqual(candidates, [])
        candidates, _ = ADAPTERS["acs"].candidates(dict(paper, landing_url="http://pubs.acs.org/article"), "html", self.settings)
        self.assertEqual(candidates[0].url, "https://pubs.acs.org/article")
        candidates, _ = ADAPTERS["acs"].candidates(paper, "xml", self.settings)
        self.assertEqual(candidates, [])

    def test_valid_original_formats(self):
        self.assertTrue(validate(XML, "xml", DOI)[0])
        self.assertTrue(validate(HTML, "html", DOI)[0])
        self.assertFalse(validate(XML, "xml", "10.1021/other")[0])
        self.assertFalse(validate(HTML, "html", "10.1021/other")[0])

    def test_abstract_login_challenge_pdf_and_invalid_xml(self):
        for body, fmt in [(b"<article><abstract><p>Abstract only</p></abstract></article>", "xml"),
                          (b"<article><body>broken", "xml"),
                          (b"%PDF-1.7 data", "html"),
                          (b"<html><h1>Sign in</h1></html>", "html"),
                          (HTML.replace(TEXT.encode(), b"Verify you are human"), "html"),
                          (b"<!DOCTYPE article [<!ENTITY x 'boom'>]><article/>", "xml")]:
            with self.subTest(fmt=fmt, body=body[:40]):
                self.assertFalse(validate(body, fmt, DOI)[0])
        abstract = HTML.replace(b'<p>', b'<div class="abstract"><p>', 1).replace(b'</p><p>', b'</p><p>', 1).replace(b'</div>', b'</div></div>', 1)
        self.assertFalse(validate(abstract, "html", DOI)[0])

    def test_springer_preview_and_metadata_are_not_fulltext(self):
        def section(title):
            return (f'<section data-title="{title}">'
                    f'<div class="c-article-section__content"><p>{TEXT}</p><p>{TEXT}</p></div>'
                    '</section>')
        metadata = section("Abstract") + section("Author information") + section("References")
        head = f'<html><head><meta name="citation_doi" content="{DOI}"></head><body>'
        landing = (head + metadata + '</body></html>').encode()
        self.assertFalse(validate(landing, "html", DOI)[0])
        preview = (head + "This is a preview of subscription content." +
                   section("Results") + metadata + '</body></html>').encode()
        self.assertFalse(validate(preview, "html", DOI)[0])
        full = (head + metadata + section("Results") + '</body></html>').encode()
        self.assertTrue(validate(full, "html", DOI)[0])

    def test_format_independent_fetch_and_resume(self):
        client = FakeClient([Response("permission_denied", http_status=403),
                             Response("success", body=XML, url="https://pubs.acs.org/full.xml", http_status=200)])
        result = fetch(self.store, self.channels(), client)
        self.assertEqual((result["success"], result["failed"]), (1, 1))
        self.assertEqual(self.store.artifact(DOI, "html")["status"], "permission_denied")
        saved = self.store.root / self.store.artifact(DOI, "xml")["path"]
        self.assertEqual(saved.read_bytes(), XML)
        resumed = FakeClient([Response("success", body=HTML, url="https://pubs.acs.org/full.html", http_status=200)])
        result = fetch(self.store, self.channels(), resumed, resume=True)
        self.assertEqual((result["success"], result["skipped"]), (1, 1))
        self.assertEqual(len(resumed.calls), 1)
        self.assertTrue(self.store.valid_file(DOI, "html"))

    def test_corrupt_and_deleted_files_redownload(self):
        fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), ("xml",))
        path = self.store.root / self.store.artifact(DOI, "xml")["path"]
        path.write_bytes(b"broken")
        self.assertFalse(self.store.valid_file(DOI, "xml"))
        data = report(self.store)
        self.assertEqual(data["any_fulltext"], 0)
        self.assertEqual(data["format_failures"]["stale_file"], 1)
        fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), ("xml",), resume=True)
        path.unlink()
        result = fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), ("xml",), resume=True)
        self.assertEqual(result["success"], 1)

    def test_failed_refresh_preserves_valid_file(self):
        fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), ("xml",))
        fetch(self.store, self.channels(), FakeClient([Response("network_error")]), ("xml",))
        self.assertTrue(self.store.valid_file(DOI, "xml"))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 2)

    def test_missing_channels_are_recorded(self):
        result = fetch(self.store, self.settings, FakeClient([]))
        self.assertEqual(result["failed"], 2)
        self.assertEqual(self.store.artifact(DOI, "html")["status"], "channel_unverified")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 2)

    def test_validation_failure_not_success(self):
        result = fetch(self.store, self.channels(), FakeClient([Response("success", body=b"<html>Abstract</html>")]), ("html",))
        self.assertEqual(result["success"], 0)
        self.assertEqual(self.store.artifact(DOI, "html")["status"], "validation_failed")

    def test_interrupted_fetch_keeps_manifest_and_resume_state(self):
        with self.assertRaises(AssertionError):
            fetch(self.store, self.channels(), FakeClient([Response("success", body=HTML)]))
        self.assertTrue((self.root / "manifest.jsonl").exists())
        self.assertTrue(self.store.valid_file(DOI, "html"))
        result = fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), resume=True)
        self.assertEqual((result["skipped"], result["success"]), (1, 1))

    def test_report_coverage_and_manual_review_survives(self):
        fetch(self.store, self.channels(), FakeClient([Response("success", body=HTML), Response("success", body=XML)]))
        data = report(self.store)
        self.assertEqual(data["publishers"]["acs"]["coverage"]["both_formats"], 1)
        self.assertIsNone(data["publishers"]["wiley"]["coverage"]["any_fulltext"])
        path = self.root / "reports" / "review.tsv"
        with path.open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        rows[0]["body_checked"] = "yes"
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
        path.write_text(out.getvalue())
        report(self.store)
        with path.open() as stream:
            self.assertEqual(next(csv.DictReader(stream, delimiter="\t"))["body_checked"], "yes")

    def test_publisher_delivery(self):
        path = self.root / "delivered.xml"
        path.write_bytes(XML)
        import_delivery(self.store, self.settings, {"doi": DOI}, path, "xml", "agreement-123")
        self.assertTrue(self.store.valid_file(DOI, "xml"))
        self.assertEqual(self.store.artifact(DOI, "xml")["access_basis"], "agreement-123")

    def test_hash_sample_expands_deterministically(self):
        for i in range(12):
            self.store.put_paper(dict(self.paper, doi=f"10.1021/test.{i}"))
        self.store.select(5, 42)
        small = {row["doi"] for row in self.store.papers()}
        self.store.select(10, 42)
        large = {row["doi"] for row in self.store.papers()}
        self.assertTrue(small < large)
        self.store.select(5, 42)
        self.assertEqual(small, {row["doi"] for row in self.store.papers()})

    def test_discovery_import_and_network_failure(self):
        path = self.root / "dois.txt"
        path.write_text(DOI + "\nhttps://doi.org/10.1021/TEST.1\n# comment\ninvalid\n")
        client = FakeClient([Response("success", body=json.dumps({"message": item()}).encode())])
        result = discover(self.store, self.settings, client, path)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(len(client.calls), 1)
        result = discover(self.store, self.settings, FakeClient([Response("network_error", detail="ProxyError")]))
        self.assertEqual(result["errors"], 1)
        data = report(self.store)
        self.assertTrue(any(e["status"] == "network_error" for e in data["discovery_errors"]))

    def test_discovery_cursor_saved_and_resumed(self):
        settings = Settings(interval=0, retries=0, keywords=("polymer",), max_pages=1, page_size=1,
                            candidates_per_publisher=200)
        page = {"message": {"items": [item("10.1016/test.1")], "next-cursor": "page-two"}}
        client = FakeClient([Response("success", body=json.dumps(page).encode()), Response("network_error")])
        discover(self.store, settings, client)
        resumed = FakeClient([Response("network_error")])
        discover(self.store, settings, resumed)
        self.assertEqual(resumed.calls[0][1]["params"]["cursor"], "page-two")

    def test_no_credentials_in_raw_metadata(self):
        paper = parse_crossref(item(URL="https://user:password@pubs.acs.org/full?token=secret",
                                   link=[{"URL": "https://pubs.acs.org/full?api_key=secret", "content-type": "text/xml"}]), self.settings)
        self.assertNotIn("secret", json.dumps(paper))
        self.assertNotIn("password", json.dumps(paper))

    def test_time_window_queries_and_stratified_selection(self):
        from paperman.corpus.discovery import queries
        settings = Settings(start_date="2000-01-01", end_date="2026-10-28", keywords=("polymer",))
        windows = list(queries(settings, "acs"))
        self.assertEqual(windows[0][2:4], ("2000-01-01", "2004-12-31"))
        self.assertEqual(windows[-1][2:4], ("2025-01-01", "2026-10-28"))
        for year in (2000, 2010, 2025):
            for i in range(4):
                self.store.put_paper(dict(self.paper, doi=f"10.1021/{year}.{i}", year=year))
        self.store.select(3, 42)
        years = {json.loads(row["metadata"])["year"] for row in self.store.papers()}
        self.assertEqual(len(years), 3)

    def test_cli_report_and_invalid_format_exit_codes(self):
        import subprocess
        import sys
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        result = subprocess.run([sys.executable, "-m", "paperman.corpus", "report", "-o", str(self.root)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "reports" / "summary.md").exists())
        result = subprocess.run([sys.executable, "-m", "paperman.corpus", "fetch", "--formats", "pdf", "-o", str(self.root)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("formats must contain", result.stdout)

    def test_secrets_in_configuration_rejected(self):
        with self.assertRaises(ValueError):
            Settings(publishers={"acs": {"xml_url": "https://pubs.acs.org/{doi}?token=SECRET"}})
        with self.assertRaises(ValueError):
            Settings(publishers={"acs": {"api_key": "SECRET"}})

    def test_review_invalidated_when_file_changes(self):
        fetch(self.store, self.channels(), FakeClient([Response("success", body=XML)]), ("xml",))
        report(self.store)
        path = self.root / "reports" / "review.tsv"
        with path.open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        rows[0]["body_checked"] = "yes"
        with path.open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        changed = XML.replace(b"Results", b"New results")
        fetch(self.store, self.channels(), FakeClient([Response("success", body=changed)]), ("xml",))
        report(self.store)
        with path.open() as stream:
            row = next(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(row["body_checked"], "")

    def test_single_paper_failure_does_not_abort_batch(self):
        self.store.put_paper(dict(self.paper, doi="10.1021/test.2"))
        self.store.select(20, 42)
        second = XML.replace(DOI.encode(), b"10.1021/test.2")
        result = fetch(self.store, self.channels(), FakeClient([Response("network_error"), Response("success", body=second)]), ("xml",))
        self.assertEqual((result["failed"], result["success"]), (1, 1))
        self.assertTrue(self.store.valid_file("10.1021/test.2", "xml"))



class FakeHTTPResponse:
    def __init__(self, status=200, body=b"ok", headers=None, url="https://api.example/test"):
        self.status_code, self.body, self.headers, self.url = status, body, headers or {}, url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def iter_content(self, size):
        yield self.body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls, self.headers, self.proxies = list(responses), [], {}, {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class NetworkTest(unittest.TestCase):
    def test_429_retry_after_and_server_retry(self):
        sleeps = []
        session = FakeSession([FakeHTTPResponse(429, headers={"Retry-After": "5"}),
                               FakeHTTPResponse(503), FakeHTTPResponse()])
        result = Client(Settings(interval=0), session, sleeps.append).get("https://api.example/test")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.retries, 2)
        self.assertIn(5, sleeps)

    def test_long_retry_after_returns_for_later(self):
        sleeps = []
        session = FakeSession([FakeHTTPResponse(429, headers={"Retry-After": "3600"})])
        result = Client(Settings(interval=0), session, sleeps.append).get("https://api.example/test")
        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(sleeps, [])

    def test_network_error_does_not_disclose_exception_secrets(self):
        session = FakeSession([requests.exceptions.ProxyError("password=SECRET")])
        result = Client(Settings(retries=0), session).get("https://api.example/test?api_key=SECRET")
        self.assertEqual(result.status, "network_error")
        self.assertNotIn("SECRET", repr(result))

    def test_cross_host_redirect_strips_custom_credentials(self):
        session = FakeSession([FakeHTTPResponse(302, headers={"Location": "https://cdn.example/full"}),
                               FakeHTTPResponse(url="https://cdn.example/full")])
        client = Client(Settings(interval=0), session)
        result = client.get("https://api.example/test", headers={"Custom-Token": "SECRET", "Accept": "text/xml"})
        self.assertEqual(result.status, "success")
        self.assertNotIn("Custom-Token", session.calls[1][1]["headers"])
        self.assertEqual(session.calls[1][1]["headers"]["Accept"], "text/xml")

    def test_unsafe_redirect_and_response_size(self):
        session = FakeSession([FakeHTTPResponse(302, headers={"Location": "http://insecure.example/full"})])
        result = Client(Settings(interval=0), session).get("https://api.example/test")
        self.assertEqual(result.status, "invalid_url")
        result = Client(Settings(interval=0, max_bytes=1), FakeSession([FakeHTTPResponse()])).get("https://api.example/test")
        self.assertEqual(result.status, "too_large")

    def test_publisher_rate_limit_shared_across_hosts(self):
        sleeps = []
        clock = lambda: 100
        client = Client(Settings(interval=10), FakeSession([FakeHTTPResponse(), FakeHTTPResponse()]), sleeps.append, clock)
        client.get("https://api.example/test", publisher="acs")
        client.get("https://pubs.example/test", publisher="acs")
        self.assertEqual(sleeps, [10])


if __name__ == "__main__":
    unittest.main()
