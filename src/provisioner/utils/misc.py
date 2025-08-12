import datetime
import os
import shlex
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import humanfriendly
from babel.dates import format_datetime

from provisioner.context import Context

context = Context.get()
logger = context.logger


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


def padding(text: str, size: int, *, on_end: bool = False) -> str:
    tl = len(text)
    if tl > size:
        return text[:size]
    elif tl < size:
        pad = (size - tl) * " "
        return f"{text}{pad}" if on_end else f"{pad}{text}"
    return text


def find_file(under: Path, named: str) -> Path:
    try:
        return next(under.rglob(named))
    except IndexError:
        return under.joinpath(named)


def get_environ() -> dict[str, str]:
    """current environment variable with langs set to C to control cli output"""
    environ = os.environ.copy()
    environ.update(
        {
            "LANG": "en_US.UTF-8",
            "LANGUAGE": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "LOCALE": "en_US.UTF-8",
        }
    )
    return environ


def get_now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)


def run_step_command(
    *args, verbose: bool = False, dont_capture: bool = False, **kwargs
) -> subprocess.CompletedProcess:

    if verbose:
        logger.info(f"Running: {shlex.join(*args)}")

    # enable capture output to make it silent if not verbose
    if not verbose and not kwargs.get("capture_output", False) and not dont_capture:
        kwargs.update({"capture_output": True})

    # set locale-related env to prevent i18n output without rewritting if passed
    env = kwargs.get("env", {})
    for key, value in get_environ().items():
        if key not in env:
            env[key] = value

    ps = subprocess.run(*args, **kwargs)  # noqa: PLW1510

    if verbose and kwargs.get("capture_output"):
        logger.info(f"Captured output ($?={ps.returncode}):\n{ps.stdout}")
    return ps
