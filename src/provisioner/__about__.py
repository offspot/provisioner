import contextlib
from pathlib import Path

__version__ = "1.0.2"


def get_version() -> str:
    return __version__


def get_provos_version() -> str:
    with contextlib.suppress(Exception):
        return Path("/etc/issue.prov").read_text().strip()
    return "Unknown"
