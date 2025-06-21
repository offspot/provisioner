from typing import Any

import click
from attrs import define, field
from halo import Halo

from provisioner.context import Context
from provisioner.host import ProvisionHost

context = Context.get()
empty_dict: dict[str, Any] = {}

ASCII_LOGO = r"""
+------------------------------------------------+
|      _    _       _                   _        |
|     | |  | |     | |                 | |       |
|     | |__| | ___ | |_ ___ _ __   ___ | |_      |
|     |  __  |/ _ \| __/ __| '_ \ / _ \| __|     |
|     | |  | | (_) | |_\__ \ |_) | (_) | |_      |
|     |_|  |_|\___/ \__|___/ .__/ \___/ \__|     |
|                          | |                   |
|                          |_|                   |
+------------------------------------------------+

""".strip()


def greet_for(name: str):
    if not context.debug:
        click.clear()
    click.secho(ASCII_LOGO, fg="white", bg="yellow", bold=True)
    logo_w = len(ASCII_LOGO.splitlines()[-1])
    about_w = len(context.about())
    click.secho(
        f" {context.about()}{(logo_w - about_w - 1) * ' '}", bg="blue", bold=True
    )
    click.echo()
    click.secho(name.upper(), fg="blue")


def success_text(text: str):
    return click.style(text, fg="green", bg="")


def error_text(text: str):
    return click.style(text, fg="red", bg="")


def warning_text(text: str):
    return click.style(text, fg="yellow", bg="")


def regular_text(text: str):
    return click.style(text, fg="", bg="")


def padding(text: str, size: int, *, on_end: bool = False) -> str:
    tl = len(text)
    if tl > size:
        return text[:size]
    elif tl < size:
        pad = (size - tl) * " "
        return f"{text}{pad}" if on_end else f"{pad}{text}"
    return text


def refresh(host: ProvisionHost):
    with Halo(text="Gathering Host information", spinner="line") as spinner:
        host.query_all()
        spinner.succeed()


@define
class CliResult:
    code: int
    offer_self_restart: bool = False
    offer_shutdown: bool = False
    do_halt: bool = False
    do_restart: bool = False
    payload: dict[str, str | int | bool] = field(default=empty_dict)
