from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .config import Settings

SECRET_NAMES = {"api_key", "apikey", "token", "access_token", "insttoken", "key", "authorization"}
SECRET_HEADERS = {"authorization", "x-els-apikey", "x-els-insttoken", "wiley-tdm-client-token"}


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    # Userinfo and fragments must never enter the manifest or logs.
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    query = [(k, "REDACTED" if k.lower() in SECRET_NAMES else v)
             for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, host, parts.path, urlencode(query), ""))


@dataclass
class Response:
    status: str
    body: bytes = b""
    url: str = ""
    http_status: int | None = None
    content_type: str = ""
    detail: str = ""
    retries: int = 0
    headers: dict = field(default_factory=dict)

    def json(self):
        import json
        return json.loads(self.body)


class Client:
    def __init__(self, settings: Settings, session=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Paperman-Corpus/0.1" +
                                     (f" (mailto:{settings.contact})" if settings.contact else "")})
        from paperman.utils.network import HTTPClient
        configured = HTTPClient().sess
        self.session.trust_env = configured.trust_env
        self.session.verify = configured.verify
        self.session.proxies = dict(configured.proxies)
        proxy = os.environ.get("PAPERMAN_CORPUS_PROXY")
        if proxy:
            self.session.trust_env = False
            self.session.proxies = {"http": proxy, "https": proxy}
        self.sleep, self.clock = sleep, clock
        self.last: dict[str, float] = {}

    def get(self, url: str, *, params=None, headers=None, publisher="") -> Response:
        interval = self.settings.publishers.get(publisher, {}).get("interval", self.settings.interval)
        request_headers = dict(headers or {})
        current = url
        retry_count = 0
        redirects = 0
        while True:
            parts = urlsplit(current)
            if parts.scheme != "https" or not parts.hostname or parts.username:
                return Response("invalid_url", url=safe_url(current), detail="HTTPS URL required")
            host = parts.hostname
            # All hosts of a publisher share a limiter (API and web front ends included).
            bucket = publisher or host
            if bucket in self.last:
                self.sleep(max(0, interval - (self.clock() - self.last[bucket])))
            self.last[bucket] = self.clock()
            try:
                with self.session.get(current, params=params, headers=request_headers,
                                      timeout=self.settings.timeout, stream=True,
                                      allow_redirects=False) as resp:
                    code = resp.status_code
                    result = Response("http_error", url=safe_url(resp.url), http_status=code,
                                      content_type=resp.headers.get("Content-Type", ""), retries=retry_count)
                    if code in (301, 302, 303, 307, 308):
                        from urllib.parse import urljoin
                        target = urljoin(resp.url, resp.headers.get("Location", ""))
                        redirects += 1
                        if redirects > 8 or target == current:
                            result.detail = "Redirect limit reached"
                            return result
                        if urlsplit(target).hostname != host:
                            request_headers = {k: v for k, v in request_headers.items()
                                               if k.lower() in {"accept", "user-agent"}}
                            # API keys in the original query are not forwarded.
                        current, params = target, None
                        continue
                    if code == 429 or 500 <= code <= 599:
                        if retry_count < self.settings.retries:
                            delay = 2 ** retry_count
                            retry_after = resp.headers.get("Retry-After", "")
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                try:
                                    until = parsedate_to_datetime(retry_after)
                                    delay = max(delay, (until - datetime.now(timezone.utc)).total_seconds())
                                except (ValueError, TypeError, OverflowError):
                                    pass
                            if delay > 60:
                                result.status = "rate_limited"
                                result.detail = "Server requested a later retry; rerun after " + retry_after
                                return result
                            self.sleep(delay)
                            retry_count += 1
                            continue
                        result.status = "rate_limited" if code == 429 else "server_error"
                        return result
                    if not 200 <= code < 300:
                        result.status = {401: "permission_denied", 403: "permission_denied",
                                         404: "not_found"}.get(code, "http_error")
                        return result
                    chunks, size = [], 0
                    for chunk in resp.iter_content(65536):
                        size += len(chunk)
                        if size > self.settings.max_bytes:
                            result.status, result.detail = "too_large", "Response exceeds max_bytes"
                            return result
                        chunks.append(chunk)
                    result.status, result.body = "success", b"".join(chunks)
                    return result
            except requests.RequestException as exc:
                if retry_count < self.settings.retries:
                    self.sleep(2 ** retry_count)
                    retry_count += 1
                    continue
                # Exception text can contain proxy credentials and API keys.
                return Response("network_error", url=safe_url(current),
                                detail=type(exc).__name__, retries=retry_count)
