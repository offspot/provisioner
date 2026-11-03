import contextlib
from pathlib import Path

__version__ = "1.0.2"


def get_version() -> str:
    return __version__


def get_provos_version() -> str:
    with contextlib.suppress(Exception):
        return Path("/etc/issue.prov").read_text().strip()
    return "Unknown"


def get_both_versions(prefix: str = "v") -> str:
    app_vers = get_version()
    os_vers = get_provos_version()
    if app_vers == os_vers:
        return f"{prefix}{app_vers}"
    return f"{prefix}{app_vers} / OS: {os_vers}"
