from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

import click
import questionary
from attrs import define
from halo import Halo

from provisioner.cli.common import CliResult, greet_for
from provisioner.cli.provision import main as provision_ep
from provisioner.cli.settings import main as settings_ep
from provisioner.cli.shell import main as shell_ep
from provisioner.cli.status import main as status_ep
from provisioner.context import Context
from provisioner.host import ProvisionHost

context = Context.get()
logger = Context.logger


def noop(host: ProvisionHost) -> CliResult:
    return CliResult(code=0)


@define
class Pane:
    name: str
    title: str
    entrypoint: Callable[[ProvisionHost], CliResult]
    selectable: bool = True


@define
class Divider(Pane):
    name: str = "---------------"
    title: str = ""
    selectable: bool = False
    entrypoint: Callable[[ProvisionHost], CliResult] = noop


Menu: TypeAlias = dict[str, Pane]


def halt(host: ProvisionHost) -> CliResult:  # noqa: ARG001
    if questionary.confirm(
        "You are about to shutdown. Are you sure?",
        default=True,
        auto_enter=False,
    ).ask():
        return CliResult(code=0, do_halt=True)
    return CliResult(code=0)


def reboot(host: ProvisionHost) -> CliResult:  # noqa: ARG001
    if questionary.confirm(
        "You are about to shutdown. Are you sure?", default=True, auto_enter=False
    ).ask():
        return CliResult(code=0, do_restart=True)
    return CliResult(code=0)


PANES: dict[str, Pane] = {
    "status": Pane(
        name="System Status", title="Hardware & System Status", entrypoint=status_ep
    ),
    "provision": Pane(
        name="Provision H1", title="Provisioning Hardware", entrypoint=provision_ep
    ),
    "settings": Pane(
        name="System Settings",
        title="Changing ProvisionOS Settings",
        entrypoint=settings_ep,
    ),
    "div1": Divider(),
    "reboot": Pane(name="Reboot (exit)", title="Restart computer", entrypoint=reboot),
    "shell": Pane(name="Shell Access", title="Shell Access", entrypoint=shell_ep),
    "div2": Divider(),
    "halt": Pane(name="Shutdown (exit)", title="Shutdown computer", entrypoint=halt),
}

main_menu = []


def display(menu: Menu) -> Pane:
    choice = None
    while not choice:
        choice = questionary.select(
            "What do you want to do?",
            choices=[
                (
                    questionary.Choice(title=entry.name, value=entry)
                    if entry.selectable
                    else questionary.Separator()
                )
                for entry in menu.values()
            ],
            use_shortcuts=True,
        ).ask()
        if not choice or not choice.selectable:
            choice = None
    return choice


def main() -> int:
    # start with status
    pane: Pane = PANES["status"]
    menu = PANES
    # payload: dict[str, Any]
    host = ProvisionHost()
    # pipe, balloon, balloon2, noise, star

    while True:
        try:
            greet_for(pane.title)
            res: CliResult = pane.entrypoint(host=host)
        except Exception as exc:
            click.secho(
                f"{pane.name} crashed. That's unexpected. "
                "Check its output and reboot.\n"
                "If it happens again, take a picture and contact Kiwix."
            )
            ...
            click.echo(exc)
            logger.exception(exc)
            break
        else:
            if res.do_halt:
                return 40
            if res.do_restart:
                return 50
        pane = display(menu)
    click.echo("OUT OF LOOP")
    return 0
