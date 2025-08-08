import click
import questionary
from halo import Halo
from log_symbols.symbols import LogSymbols

from provisioner.cli.common import CliResult, padding
from provisioner.cli.provision_manual import main as main_prog
from provisioner.constants import RC_CANCELED
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.utils.blk.devices import Disk
from provisioner.utils.imgprobe import ImageFileInfo
from provisioner.utils.misc import format_size

context = Context.get()
logger = context.logger

CLEAR_LINE: str = Halo.CLEAR_LINE
SUCC = LogSymbols.SUCCESS.value
ERR = LogSymbols.ERROR.value

def main(host: ProvisionHost) -> CliResult:

    click.secho(r" /!\ WARNING This will trigger a complete Kiwix H1 Provisioning")

    images_styles = questionary.Style(
        [
            ("kiwix-hotspot", "fg:green"),
            ("raspi", "fg:yellow"),
            ("other", "fg:red"),
        ]
    )

    cancel_choice = questionary.Choice(title="Exit Provisioning", value="cancel")
    image_index: int | str = questionary.select(
        "Select Image to Flash on Disk",
        choices=[
            questionary.Choice(
                title=f"{padding(format_size(img.size), 8)} {img.human}", value=index
            )
            for index, img in enumerate(host.dev.images)
        ]
        + [questionary.Separator(), cancel_choice],
        # use_search_filter=True,
        use_jk_keys=False,
        # use_shortcuts=True,
        style=images_styles,
    ).ask()
    if isinstance(image_index, str) or image_index == cancel_choice.value:
        return CliResult(code=RC_CANCELED)
    image = host.dev.images[image_index]
    image_device = host.dev.get_disk_from_name(image.device)
    image_phy_disk = getattr(image_device, "disk") or image_device

    click.echo("Image: ", nl=False)
    click.secho(image.linux.release, fg="magenta", nl=False)
    click.echo(" Variant: ", nl=False)
    click.secho(image.linux.variant, fg="magenta", nl=False)
    click.echo(" Version: ", nl=False)
    click.secho(image.linux.version, fg="magenta")
    click.secho(f"Disk: {image_device} ({image_device.name})")
    click.secho(f"File on disk: {image.path_root}{image.fpath.name}")

    def disabled(disk: Disk, image: ImageFileInfo) -> str | None:
        if disk.name == image_phy_disk.name:
            return "Source disk of selected image"
        if host.dev.provisionos_disk and disk.name == host.dev.provisionos_disk.name:
            return "ProvisionOS disk"
        if image.size > disk.size:
            return f"Too small for {format_size(image.size)} image"

    target_disk_name: str = questionary.select(
        "Select Target Disk",
        choices=[
            questionary.Choice(
                title=f"{disk!s} ({disk.name})",
                value=key,
                disabled=disabled(disk, image),
            )
            for key, disk in host.dev.disks.items()
        ]
        + [questionary.Separator(), cancel_choice],
        # use_search_filter=True,
        use_jk_keys=False,
        use_shortcuts=True,
        style=images_styles,
    ).ask()
    if target_disk_name == cancel_choice.value:
        return CliResult(code=RC_CANCELED)
    target_disk = host.dev.disks[target_disk_name]

    click.secho(r" /!\ ATTENTION! ", bg="red", fg="white")
    click.secho(
        f"You are about to start Provisioning on {target_disk!s} ({target_disk.path})"
    )
    click.secho("Once you start, all data on this disk will be gone forever.")
    if not questionary.confirm(
        f"Continue and Provision {target_disk!s}?", default=False, auto_enter=False
    ).ask():
        return CliResult(code=RC_CANCELED)

    return main_prog(
            source_device_path=image_device.path,
            source_image_path=image.relpath,
            target=target_disk.path,
        )

    return CliResult(code=0)
