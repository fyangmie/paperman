#!/usr/bin/env python3
"""Securely configure the Springer Nature Open Access API key for paperman."""
import getpass
import json
import os
import tempfile
from pathlib import Path


def main():
    key = getpass.getpass("Springer Nature Open Access API key (hidden): ").strip()
    if not key:
        raise SystemExit("Empty key; nothing saved")
    target = Path.home() / ".config" / "paperman" / "springer-credentials.json"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".springer-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"api_key": key}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Springer API key saved with owner-only permissions.")
    print("Paperman will use it automatically for Springer Nature XML requests.")


if __name__ == "__main__":
    main()
