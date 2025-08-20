import os
import subprocess

import click

from provisioner.cli.common import CliResult
from provisioner.host import ProvisionHost


def main(host: ProvisionHost) -> CliResult:  # noqa: ARG001
    click.secho(r" /!\ WARNING /!\ ", bg="red", fg="white", bold=True)
    click.secho("You are entering a shell as root. ProvisionOS is not stateless.")
    click.secho("Modifications you make here might persist over future runs.")
    click.secho("This is strictly reserved to users who know what they're doing.")
    click.secho("If unsure (or once done), type: ", nl=False, fg="yellow")
    click.secho("exit", nl=False, bold=True, fg="yellow")
    click.secho(" (then enter) to go back to the menu.", fg="yellow")
    env = os.environ
    env.update({"NOKIOSK": "1"})
    subprocess.run([os.getenv("SHELL") or "sh"], env=env, check=False)

    return CliResult(code=0)
