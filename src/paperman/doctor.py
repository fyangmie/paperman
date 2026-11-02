"""Read-only diagnostics; network probes require --online."""

import argparse, json, os, sys
from urllib.parse import urlsplit
from .utils.network import HTTPClient, CONFIG_PATH
from .corpus.network import Client
from .corpus.config import Settings


def describe(session):
    effective = session.merge_environment_settings("https://ipinfo.io/json", {}, False, None, None)["proxies"]
    return {
        "effective_proxy_hosts_for_probe": {k: urlsplit(v).hostname for k, v in effective.items() if k in ("http", "https", "all")},
        "trust_environment": session.trust_env,
        "proxy_hosts": {k: urlsplit(v).hostname for k, v in session.proxies.items()},
        "tls_verification": bool(session.verify),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--online", action="store_true", help="Query ipinfo.io through PDF and corpus clients")
    args = p.parse_args()
    pdf = HTTPClient()
    corpus = Client(Settings())
    result = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "config": str(CONFIG_PATH),
        "pdf": describe(pdf.sess),
        "corpus": describe(corpus.session),
        "scihub_proxy_configured": bool(os.environ.get("PAPERMAN_SCIHUB_PROXY")),
        "note": "A campus-looking IP alone does not prove article access rights.",
    }
    if args.online:
        for name, session in [("pdf", pdf.sess), ("corpus", corpus.session)]:
            try:
                r = session.get("https://ipinfo.io/json", timeout=15)
                r.raise_for_status()
                d = r.json()
                result[name]["exit"] = {k: d.get(k) for k in ("ip", "org", "country")}
            except Exception as exc:
                result[name]["error"] = type(exc).__name__
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
