"""User-owned data locations, independent of checkout/install directory."""

import os
from pathlib import Path


def corpus_directory():
    return Path(os.environ.get("PAPERMAN_DATA_DIR", str(Path.home() / "Documents" / "paperman"))) / "corpus"
