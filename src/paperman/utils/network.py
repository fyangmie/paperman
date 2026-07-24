from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from typing import Optional

import requests


CONFIG_PATH = Path.home() / ".config" / "paperman" / "config.ini"


def _load_proxy() -> str:
    cfg = ConfigParser()
    try:
        if CONFIG_PATH.exists():
            cfg.read(CONFIG_PATH)
            return cfg.get("settings", "proxy", fallback="")
    except Exception:
        pass
    return ""


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
        if proxy:
            self.sess.proxies = {"http": proxy, "https": proxy}
        else:
            self.sess.proxies = {}

    def reload_proxy(self) -> None:
        self._apply_proxy()

    def get(self, url: str, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            return None

    def head(self, url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.head(url, timeout=timeout, allow_redirects=True, **kwargs)
            return resp
        except requests.RequestException:
            return None

    def post(self, url: str, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.sess.post(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            return None


http = HTTPClient()
