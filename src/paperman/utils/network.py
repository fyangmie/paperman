from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from typing import Optional

import requests
import os
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


CONFIG_PATH = Path(os.environ.get("PAPERMAN_CONFIG", str(Path.home() / ".config" / "paperman" / "config.ini"))).expanduser()


def _load_proxy() -> str:
    cfg = ConfigParser()
    try:
        if CONFIG_PATH.exists():
            cfg.read(CONFIG_PATH)
            return cfg.get("settings", "proxy", fallback="")
    except Exception:
        pass
    return ""


def _load_proxy_mode() -> str:
    cfg = ConfigParser()
    try:
        if CONFIG_PATH.exists():
            cfg.read(CONFIG_PATH)
            return cfg.get("settings", "proxy_mode", fallback="auto").strip().lower()
    except Exception:
        pass
    return "auto"


class HTTPClient:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": "Paperman/0.1 (mailto:paperman@localhost)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._apply_proxy()

    def _apply_proxy(self) -> None:
        proxy = _load_proxy()
        direct = _load_proxy_mode() == "direct"
        self.sess.trust_env = not (direct or proxy)
        # Keep explicit CA configuration even when bypassing environment proxies.
        self.sess.verify = ((os.environ.get("REQUESTS_CA_BUNDLE")
                             or os.environ.get("CURL_CA_BUNDLE") or True) if not self.sess.trust_env else True)
        if proxy and not direct:
            self.sess.proxies = {"http": proxy, "https": proxy}
        else:
            self.sess.proxies = {}

    def _diagnose(self, url, resp=None, error=None):
        target = os.environ.get("PAPERMAN_DIAGNOSTICS")
        if not target:
            return
        def clean(value):
            parts = urlsplit(value or "")
            return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
        row = {"time": datetime.now(timezone.utc).isoformat(),
               "doi": os.environ.get("PAPERMAN_CURRENT_DOI", ""),
               "source": os.environ.get("PAPERMAN_CURRENT_SOURCE", ""),
               "url": clean(url), "error": error}
        if resp is not None:
            body = resp.content or b""
            text = body[:100000].lower()
            challenge = (resp.headers.get("cf-mitigated") == "challenge"
                         or b"<title>ddos-guard" in text
                         or b"<title>just a moment" in text)
            row.update(status=resp.status_code, final_url=clean(resp.url),
                       content_type=resp.headers.get("Content-Type", ""),
                       bytes=len(body), challenge=challenge,
                       is_pdf=b"%PDF" in body[:1024])
        try:
            with open(target, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def reload_proxy(self) -> None:
        self._apply_proxy()

    def get(self, url: str, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.get(url, timeout=timeout, **kwargs)
            self._diagnose(url, resp=resp)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if exc.response is None:
                self._diagnose(url, error=type(exc).__name__)
            return None

    def head(self, url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.head(url, timeout=timeout, allow_redirects=True, **kwargs)
            self._diagnose(url, resp=resp)
            return resp
        except requests.RequestException as exc:
            if exc.response is None:
                self._diagnose(url, error=type(exc).__name__)
            return None

    def post(self, url: str, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.post(url, timeout=timeout, **kwargs)
            self._diagnose(url, resp=resp)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if exc.response is None:
                self._diagnose(url, error=type(exc).__name__)
            return None


http = HTTPClient()
