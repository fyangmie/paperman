from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode, urlsplit

from .config import Settings


@dataclass
class Candidate:
    url: str
    source: str
    access_basis: str
    headers: dict = field(default_factory=dict, repr=False)


class PublisherAdapter:
    """Shared discovery for deposited TDM links and explicitly configured channels."""
    name = ""
    domains: tuple[str, ...] = ()

    def owns(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)

    def candidates(self, paper: dict, fmt: str, settings: Settings) -> tuple[list[Candidate], str]:
        options = settings.publishers.get(self.name, {})
        found = []
        template = options.get(fmt + "_url")
        token_env = options.get("token_env", "")
        token = os.environ.get(token_env, "") if token_env else ""
        headers = {}
        if token:
            header = options.get("token_header", "Authorization")
            headers[header] = options.get("token_prefix", "") + token
        if template and (not token_env or token):
            found.append(Candidate(template.format(doi=quote(paper["doi"], safe="/")),
                                   self.name + ":configured", "institution_tdm", headers))
        for link in paper.get("links", []):
            mime = link.get("content_type", "").lower()
            matches = "xml" in mime if fmt == "xml" else "html" in mime
            # Off-domain deposits need a separately configured channel; never send credentials there.
            if matches and self.owns(link["url"]):
                found.append(Candidate(link["url"], self.name + ":crossref", "deposited_fulltext_link", headers))
        if fmt == "html":
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).date().isoformat()
            open_license = False
            for license in paper.get("licenses", []):
                parts = urlsplit(license.get("url", ""))
                starts = (license.get("start") or {}).get("date-time", "")[:10]
                if (parts.hostname in {"creativecommons.org", "www.creativecommons.org"}
                        and parts.path.startswith(("/licenses/", "/publicdomain/"))
                        and (not starts or starts <= today)):
                    open_license = True
                    break
            landing = paper.get("landing_url", "")
            if landing.startswith("http://"):
                landing = "https://" + landing[7:]
            if open_license and landing.startswith("https://") and self.owns(landing):
                found.append(Candidate(landing, self.name + ":oa_landing", "open_access"))
        if fmt == "html" and options.get("html_enabled", False):
            landing = paper.get("landing_url", "")
            if self.owns(landing):
                found.append(Candidate(landing, self.name + ":html", "institution_html_tdm", headers))
            else:
                # DOI resolver is used without publisher credentials.
                found.append(Candidate("https://doi.org/" + quote(paper["doi"], safe="/"),
                                       self.name + ":doi", "institution_html_tdm"))
        if found:
            return found, ""
        if token_env and not token:
            return [], "missing_credentials"
        return [], "channel_unverified"


class ElsevierAdapter(PublisherAdapter):
    name = "elsevier"
    domains = ("elsevier.com", "sciencedirect.com")

    def candidates(self, paper, fmt, settings):
        found, reason = super().candidates(paper, fmt, settings)
        if fmt == "xml":
            options = settings.publishers.get(self.name, {})
            key = os.environ.get(options.get("api_key_env", "ELSEVIER_API_KEY"), "")
            if key:
                headers = {"X-ELS-APIKey": key, "Accept": "text/xml"}
                inst = os.environ.get(options.get("insttoken_env", "ELSEVIER_INSTTOKEN"), "")
                if inst:
                    headers["X-ELS-Insttoken"] = inst
                found.insert(0, Candidate("https://api.elsevier.com/content/article/doi/" +
                                          quote(paper["doi"], safe="/") + "?view=FULL",
                                          "elsevier:api", "institution_tdm", headers))
            elif not found:
                reason = "missing_credentials"
        return found, reason


class SpringerNatureAdapter(PublisherAdapter):
    name = "springer_nature"
    domains = ("springernature.com", "springer.com", "nature.com", "biomedcentral.com")

    def candidates(self, paper, fmt, settings):
        found, reason = super().candidates(paper, fmt, settings)
        if fmt == "xml":
            options = settings.publishers.get(self.name, {})
            key = os.environ.get(options.get("oa_api_key_env", "SPRINGER_NATURE_API_KEY"), "")
            if not key:
                # Keep API credentials out of project config and allow the local setup helper.
                from pathlib import Path
                import json
                credential_file = Path.home() / ".config" / "paperman" / "springer-credentials.json"
                try:
                    if credential_file.exists():
                        if credential_file.stat().st_mode & 0o077:
                            raise PermissionError("Springer credential file must have mode 600")
                        key = json.loads(credential_file.read_text()).get("api_key", "")
                except (OSError, ValueError, TypeError):
                    key = ""
            if key:
                query = urlencode({"q": "doi:" + paper["doi"], "api_key": key, "p": 1})
                found.append(Candidate("https://api.springernature.com/openaccess/jats?" + query,
                                       "springer_nature:oa_api", "open_access"))
            elif not found:
                reason = "missing_credentials"
        return found, reason


class ACSAdapter(PublisherAdapter):
    name = "acs"
    domains = ("acs.org",)


class RSCAdapter(PublisherAdapter):
    name = "rsc"
    domains = ("rsc.org",)


class WileyAdapter(PublisherAdapter):
    name = "wiley"
    domains = ("wiley.com",)

    def candidates(self, paper, fmt, settings):
        found, reason = super().candidates(paper, fmt, settings)
        return found, reason if found else ("missing_credentials" if reason == "missing_credentials" else "format_unavailable")


ADAPTERS = {adapter.name: adapter() for adapter in
            (ElsevierAdapter, SpringerNatureAdapter, ACSAdapter, RSCAdapter, WileyAdapter)}
