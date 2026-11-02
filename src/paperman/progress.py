"""Optional structured stage events, without request credentials or URLs."""
import json
import os
import time
from pathlib import Path


def stage(name, **details):
    target = os.environ.get("PAPERMAN_STAGES")
    if target:
        with Path(target).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"stage": name, "time": time.time(), **details}) + "\n")
