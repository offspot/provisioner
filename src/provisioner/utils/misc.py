import datetime
import os
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import humanfriendly
from babel.dates import format_datetime


def format_size(size: int, *, binary: bool = False) -> str:
    return humanfriendly.format_size(size, binary=binary)


def format_duration(seconds: int | float) -> str:
    return humanfriendly.format_timespan(num_seconds=seconds, detailed=False)


def format_speed(size: int, duration: int | float) -> str:
    return f"{format_size(size // int(duration))}/s"


def yesno(value: Any) -> str:
    """yes or no string from bool value"""
    return "yes" if bool(value) else "no"


def format_dt(
    dt: datetime.datetime, fmt: str = "long", locale: str | None = None
) -> str:
    return format_datetime(dt, fmt, locale=locale or "en_US.UTF-8")


def run_command(args: list[str]) -> CompletedProcess[str]:
    ps = subprocess.run(
        args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    return CompletedProcess(
        args=ps.args,
        returncode=ps.returncode,
        stdout=ps.stdout.strip() if ps.stdout else "",
    )


def find_file(under: Path, named: str) -> Path:
    try:
        return next(under.rglob(named))
    except IndexError:
        return under.joinpath(named)


def get_environ() -> dict[str, str]:
    """current environment variable with langs set to C to control cli output"""
    environ = os.environ.copy()
    environ.update({"LANG": "C", "LC_ALL": "C"})
    return environ


def get_now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)
