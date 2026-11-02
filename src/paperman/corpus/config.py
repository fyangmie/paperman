from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

PUBLISHERS = ("elsevier", "springer_nature", "acs", "rsc", "wiley")
PREFIXES = {
    "elsevier": ("10.1016",),
    "springer_nature": ("10.1007", "10.1038", "10.1186"),
    "acs": ("10.1021",), "rsc": ("10.1039",),
    "wiley": ("10.1002", "10.1111"),
}
KEYWORDS = ("polymer", "polymeric", "copolymer", "polyethylene", "polypropylene",
            "polystyrene", "polyurethane", "polyamide", "polyester")


def normalize_doi(value: str) -> str:
    value = value.strip()
    if value.lower().startswith(("https://doi.org/", "http://doi.org/", "https://dx.doi.org/")):
        value = unquote(urlsplit(value).path.lstrip("/"))
    value = re.sub(r"^doi:\s*", "", value, flags=re.I).strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value):
        raise ValueError("Invalid DOI: " + value[:100])
    return value


def publisher_for(doi: str, name: str = "") -> str:
    for publisher, prefixes in PREFIXES.items():
        if doi.split("/", 1)[0] in prefixes:
            return publisher
    name = name.lower()
    for publisher, aliases in {
        "elsevier": ("elsevier",), "springer_nature": ("springer", "nature"),
        "acs": ("american chemical society",), "rsc": ("royal society of chemistry",),
        "wiley": ("wiley",),
    }.items():
        if any(alias in name for alias in aliases):
            return publisher
    return "other"


def document_id(doi: str) -> str:
    return hashlib.sha256(normalize_doi(doi).encode()).hexdigest()


@dataclass
class Settings:
    start_date: str = "2000-01-01"
    end_date: str = field(default_factory=lambda: date.today().isoformat())
    keywords: tuple[str, ...] = KEYWORDS
    per_publisher: int = 20
    candidates_per_publisher: int = 200
    seed: int = 42
    page_size: int = 100
    max_pages: int = 3
    interval: float = 10.0
    retries: int = 3
    timeout: float = 45.0
    max_bytes: int = 50 * 1024 * 1024
    openalex: bool = False
    contact: str = ""
    publishers: dict = field(default_factory=dict)

    def __post_init__(self):
        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date must precede end_date")
        if not self.keywords or any(not word.strip() for word in self.keywords):
            raise ValueError("keywords must contain non-empty words")
        for key in ("per_publisher", "candidates_per_publisher", "page_size", "max_pages", "max_bytes"):
            if getattr(self, key) <= 0:
                raise ValueError(key + " must be positive")
        if self.page_size > 1000 or self.per_publisher > self.candidates_per_publisher:
            raise ValueError("page_size <= 1000 and per_publisher <= candidates_per_publisher required")
        if self.interval < 0 or self.timeout <= 0 or not 0 <= self.retries <= 10:
            raise ValueError("Invalid network limits")
        if set(self.publishers) - set(PUBLISHERS):
            raise ValueError("Unknown publisher configuration")
        allowed = {"interval", "html_url", "xml_url", "html_enabled", "token_env", "token_header",
                   "token_prefix", "api_key_env", "insttoken_env", "oa_api_key_env"}
        for options in self.publishers.values():
            if set(options) - allowed:
                raise ValueError("Unknown publisher options; use token_env for credentials")
            if options.get("interval", self.interval) < 0:
                raise ValueError("Publisher interval must be non-negative")
            for key in ("html_url", "xml_url"):
                if key in options:
                    template = options[key]
                    if not template.startswith("https://") or "{doi}" not in template:
                        raise ValueError(key + " must be an HTTPS URL containing {doi}")
                    template.format(doi="10.0000/example")
                    parts = urlsplit(template)
                    secret_keys = {"api_key", "apikey", "token", "access_token", "insttoken", "key", "authorization"}
                    if parts.username or any(k.lower() in secret_keys for k, _ in parse_qsl(parts.query)):
                        raise ValueError("URL credentials must be supplied using environment variables")

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        if path is None:
            return cls()
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        corpus = dict(data.get("corpus", {}))
        network = dict(data.get("network", {}))
        unknown = set(data) - {"corpus", "network", "publishers"}
        if unknown:
            raise ValueError("Unknown sections: " + ", ".join(sorted(unknown)))
        if "keywords" in corpus:
            corpus["keywords"] = tuple(corpus["keywords"])
        return cls(**corpus, **network, publishers=data.get("publishers", {}))
