from pathlib import Path

import click
from attrs import asdict
from halo import Halo

from provisioner.cli.common import CliResult, refresh
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.provisioning.common import Environment
from provisioner.provisioning.manager import ProvisionManager
from provisioner.utils.blk.devices import Device, Disk
from provisioner.utils.misc import format_duration, format_size

logger = Context.logger


def main(
    source_device_path: Path,
    source_image_path: Path,
    target: Path,
    *,
    assume_yes: bool = False,
) -> CliResult:

    click.echo(
        "Requested Provisioning for:\n"
        f"  {source_image_path=!s}\n"
        f"  {source_device_path=!s}\n"
        f"  {target=!s}"
    )

    host = ProvisionHost()
    refresh(host)

    try:
        image_device = host.dev.get_disk_from_path(source_device_path)
    except KeyError:
        click.secho(f"Source device ({source_device_path}) not found", fg="red")
        return CliResult(code=3)

    if image_device.parent:
        payload = (
            asdict(image_device.parent)
            if isinstance(image_device.parent, Device)
            else image_device.parent
        )
        img_dev_root = Disk(**payload).path
    else:
        img_dev_root = image_device.path

    if img_dev_root not in [d.path for d in host.dev.source_disks] and not assume_yes:
        if not click.confirm(
            f"Source device ({image_device}) not identified as a source disk. Continue?"
        ):
            return CliResult(code=2)
    if not image_device:
        click.secho(f"Cannot find source device {image_device}", fg="red")
        return CliResult(code=3)

    image = None
    for imageinfo in host.dev.images:
        if (
            imageinfo.device == image_device.path.name
            and imageinfo.relpath == source_image_path
        ):
            image = imageinfo
    if not image:
        click.secho(
            f"Cannot find source image {source_image_path} on {image_device}", fg="red"
        )
        return CliResult(code=3)

    target_disk = None
    for device in host.dev.disks.values():
        if device.path == target:
            target_disk = device
    if target_disk not in host.dev.target_disks and not assume_yes:
        if not click.confirm(
            f"Target device ({target_disk}) not identified as a target disk."
        ):
            return CliResult(code=2)
    if not target_disk:
        click.secho(f"Cannot find target device {target}", fg="red")
        return CliResult(code=3)

    environment = Environment(
        host=host, image=image, image_device=image_device, target_disk=target_disk
    )

    if not environment.image_fits_target:
        click.secho(
            f"Image {environment.image.name} ({format_size(environment.image.size)}) "
            f"does not fit target {environment.target_disk}",
            fg="red",
        )
        return CliResult(code=5)

    click.secho(
        f"Starting Provisioning:\n"
        f"  Image: {environment.image.name} "
        f"(/dev/{environment.image.device}:{environment.image.relpath})\n"
        f"  Target disk: {environment.target_disk} ({environment.target_disk.path})",
        fg="blue",
    )

    manager = ProvisionManager(environment=environment)
    failed = False
    with manager as runner:
        for step in runner:
            try:
                spinner = Halo(text=f"{step.prefix} {step.name}", spinner="line")
                click.secho("/", fg="cyan", nl=False)
                click.echo(f" {step.prefix} {step.name}")

                res = step.run(verbose=True)
                if res.succeeded:
                    spinner.succeed(f"{step.prefix} {step.name} {res.success_text}")
                else:
                    failed = True
                    spinner.fail(f"{step.prefix} {step.name} {res.error_text}")
                    logger.debug(res.debug_text)
                    break
            except Exception as exc:
                logger.error(f"Step {step.stepnum} failed: {exc}")
                logger.debug(exc)
                logger.exception(exc)
                return CliResult(code=1)
    if not failed:
        click.secho("Provisioning completed successfuly 🎉", fg="green")
    click.echo(
        f"  Image: {image.name} (/dev/{image.device}:{image.relpath})\n"
        f"  Target disk: {target_disk} ({target_disk.path})\n"
        f"  Duration: {format_duration(manager.duration)}"
    )
    click.echo("Please reboot.")

    return CliResult(code=1 if failed else 0)
