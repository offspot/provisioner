from typing import Any

import click
from attrs import define, field
from halo import Halo

from provisioner.context import Context
from provisioner.host import ProvisionHost

context = Context.get()
empty_dict: dict[str, Any] = {}


def greet_for(name: str):
    if not context.debug:
        click.clear()
    about_w = len(context.about())
    click.secho(f" {context.about()}{(about_w - 1) * ' '}", bg="blue", bold=True)
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


def refresh(host: ProvisionHost):
    with Halo(text="Gathering Host information", spinner="line") as spinner:
        host.query_all()
        spinner.succeed()


@define
class CliResult:
    code: int
    exit_with_code: bool = False
    payload: dict[str, str | int | bool] = field(default=empty_dict)
