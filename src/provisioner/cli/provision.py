import datetime
import errno
import os
import pty
import re
import select
import shutil
import subprocess
import time
from collections.abc import Generator
from threading import Thread

import click
import questionary
from halo import Halo
from log_symbols.symbols import LogSymbols
from nmcli.data.device import Device

from provisioner.cli.common import CliResult, padding
from provisioner.constants import RC_CANCELED
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.utils.blk.devices import Disk
from provisioner.utils.blk.misc import mount_to_temp, timed_unmount
from provisioner.utils.imgprobe import ImageFileInfo
from provisioner.utils.misc import format_duration, format_size, format_speed, get_now

context = Context.get()
logger = context.logger

CLEAR_LINE: str = Halo.CLEAR_LINE
SUCC = LogSymbols.SUCCESS.value
ERR = LogSymbols.ERROR.value


class RpiImager:
    stdout: str
    ps: subprocess.Popen[str]

    def __init__(self, args: list[str], **kwargs: dict[str, str]) -> None:
        self.args = args

        self.started_on: datetime.datetime = datetime.datetime.now(tz=datetime.UTC)
        self.ended_on: datetime.datetime | None = None

        self.img_hash: str = ""
        self.verify_hash: str = ""

        self.preparing_done: bool = False
        self.write_progress: int = 0
        self.write_done: bool = False
        self.write_duration: float = 0
        self.verify_progress: int = 0
        self.verify_done: bool = False
        self.verify_duration: float = 0
        self.finalizing_done: bool = False

        self.stdout: str = ""

        self.master_stdout, self.slave_stdout = pty.openpty()

        self.output_reader = Thread(target=self.consume_pty)

    def start(
        self,
    ):

        self.ps = subprocess.Popen(
            self.args,
            text=True,
            encoding="UTF-8",
            bufsize=1,
            stdout=self.slave_stdout,
            stderr=subprocess.STDOUT,
            close_fds=True,
            env=os.environ,
        )
        os.close(self.slave_stdout)
        self.output_reader.start()

    def consume_pty(self):
        while self.ps.returncode is None:
            self.read_output()
            self.parse()

    def read_output(self):
        bufsize = 1024
        timeout = 0.5  # seconds
        readable = [self.master_stdout]
        try:
            ready, _, _ = select.select(readable, [], [], timeout)
            if ready:
                for fd in ready:
                    try:
                        data = os.read(fd, bufsize)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise exc
                        # EIO means EOF on some systems
                        readable.remove(fd)
                        break
                    else:
                        if not data:  # EOF
                            break
                        content = (
                            data.replace(b"\r\n", b"\n")
                            .replace(b"\r", b"\n")
                            .decode("UTF-8")
                        )
                        self.stdout += content
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise exc
            # looks like ps has ended. let's let rest of func cleanup
            logger.debug(f"READ attempt on bad descriptor ; maybe ended? -- {exc}")

        if self.completed:
            logger.debug("UPDATE found ps ended")
            if not self.ended_on:
                self.ended_on = datetime.datetime.now(tz=datetime.UTC)
            try:
                os.close(self.master_stdout)
            except Exception as exc:
                logger.debug(f"Failed to release master stdout: {exc}")
            return

    @property
    def suceeded(self) -> bool:
        return self.ps.returncode == 0

    @property
    def completed(self) -> bool:
        return self.ps.poll() is not None

    @property
    def duration(self) -> int:
        if not self.ended_on:
            self.ended_on = datetime.datetime.now(tz=datetime.UTC)
        return int((self.ended_on - self.started_on).total_seconds())

    @property
    def progress(self) -> int:
        return (min(100, self.write_progress) + min(100, self.verify_progress)) // 2

    @property
    def step(self) -> str:
        if not self.preparing_done:
            return "Preparing (device and hashes)"
        if not self.write_done:
            return "Writing to disk"
        if not self.verify_done:
            return "Verifying disk"
        if not self.finalizing_done:
            return "Finalizing"
        return "Completed"

    @property
    def returncode(self) -> int:
        return self.ps.returncode

    def update(self) -> bool:
        """whether it has completed"""

        self.parse()

        if self.completed:
            logger.debug("!!UPDATE found ps ended")
            if not self.ended_on:
                self.ended_on = datetime.datetime.now(tz=datetime.UTC)
            return True
        return False

    def wait(self, timeout: float | None = None) -> int:
        return self.ps.wait(timeout=timeout)

    def parse(self):
        if self.finalizing_done:  # already fully parsed
            return
        lines = self.stdout.splitlines()

        if not self.preparing_done:
            for line in lines:
                if "Writing:" in line or "Done zeroing out" in line:
                    self.preparing_done = True
                    break

        if not self.img_hash:
            for line in lines:
                if match := re.match(
                    r"^Hash of uncompressed image: \"(?P<hash>[a-z0-9]+)\"$", line
                ):
                    self.img_hash = match.groupdict()["hash"]
                    break

        if not self.write_done:
            for line in lines:
                if line.startswith("  Writing:"):
                    if match := re.match(
                        r"^  Writing: (.+)] (?P<percent>\d+) %$", line
                    ):
                        self.write_progress = int(match.groupdict()["percent"])

                if line.startswith("Write done ") or line.startswith("  Verifying:"):
                    self.write_done = True
                    self.write_progress = 100
                    if match := re.match(
                        r"^Write done in (?P<seconds>\d+) seconds.*", line
                    ):
                        self.write_duration = float(match.groupdict()["seconds"])
                        break

        if not self.verify_done:
            for line in lines:
                if line.startswith("  Verifying:"):
                    if match := re.match(
                        r"^  Verifying: (.+)] (?P<percent>\d+) %$", line
                    ):
                        self.verify_progress = int(match.groupdict()["percent"])

                if (
                    line.startswith("Verify done")
                    or line.startswith("Verify hash:")
                    or line.startswith("Writing first block")
                ):
                    self.verify_done = True
                    self.verify_progress = 100
                    if match := re.match(
                        r"^Verify done in (?P<seconds>[\d\.]+) seconds.*", line
                    ):
                        self.verify_duration = float(match.groupdict()["seconds"])
                        break

        if self.verify_done and not self.verify_hash:
            for line in lines:
                if match := re.match(r"^Verify hash: \"(?P<hash>[a-z0-9]+)\"$", line):
                    self.verify_hash = match.groupdict()["hash"]
                    break

        if not self.finalizing_done:
            for line in lines:
                if line.startswith("Write successful"):
                    self.finalizing_done = True
                    break


class Step:

    ident: str = ""
    name: str = ""
    no_progress: bool = False

    def __init__(
        self,
        *,
        host: ProvisionHost,
        image: ImageFileInfo,
        image_device: Device,
        target_disk: Disk,
        step_index: int,
        total_steps: int,
    ):
        self.host = host
        self.image = image
        self.image_device = image_device
        self.target_disk = target_disk
        self.step_index = step_index
        self.total_steps = total_steps

    @property
    def stepnum(self) -> int:
        return self.step_index + 1

    @property
    def prefix(self) -> str:
        return f"[Step {self.stepnum}/{self.total_steps}]"

    def run(self) -> int: ...
    def cleanup(self) -> int: ...


class ImagerStep(Step):

    ident: str = "imager"
    name: str = "Flash image onto target disk"
    no_progress: bool = True

    def run(self) -> int:
        my_prefix = f"{self.prefix} [imager] "
        my_prefix_succ = f"{CLEAR_LINE}{SUCC} {my_prefix}"

        with Halo(
            text=f"{self.prefix} Mounting source partition", spinner="line"
        ) as spinner:
            mountpoint = mount_to_temp(self.image_device.path)
            fpath = mountpoint.joinpath(self.image.relpath)
            spinner.succeed("Mounted source partition")
        try:
            imager_bin = shutil.which("rpi-imager")
            assert imager_bin

            imager = RpiImager(
                args=[
                    imager_bin,
                    "--cli",
                    "--disable-eject",
                    "--debug",
                    str(fpath),
                    str(self.target_disk.path),
                ]
            )
            imager.start()
            prepare_started_on = get_now()
            progress: int = 0
            new_progress: int = 0

            click.echo(f"{my_prefix}{imager.step}...")
            while not imager.update() and not imager.preparing_done:
                ...
            prepare_duration = (get_now() - prepare_started_on).total_seconds()
            click.secho(
                f"{my_prefix_succ} Prepared in {format_duration(prepare_duration)}"
            )

            with click.progressbar(
                length=100,
                label=padding(f"{my_prefix}Writing {self.image.name}", 42),
            ) as bar:
                bar.update(0, current_item=imager.step)
                while not imager.update():
                    if imager.write_done:
                        bar.update(100 - progress)
                        break
                    new_progress = imager.write_progress
                    bar.update(new_progress - progress)
                    progress = new_progress
                bar.update(100)  # too much but OK

            progress = new_progress = 0
            with click.progressbar(
                length=100,
                label=padding(f"{my_prefix}Verifying {self.target_disk}", 42),
            ) as bar:

                while not imager.update():
                    if imager.verify_done:
                        bar.update(100 - progress)
                        break
                    new_progress = imager.verify_progress
                    bar.update(new_progress - progress)
                    progress = new_progress
                bar.update(100)  # too much but OK

            with Halo(text=f"{my_prefix}{imager.step}", spinner="line") as spinner:
                imager.wait()
                spinner.succeed()

            if imager.suceeded:
                click.secho(
                    f"{self.prefix} [imager] {self.image.name} "
                    f"written successfuly to {self.target_disk!s}",
                    fg="green",
                    bold=True,
                )
                click.echo(
                    f"Flashed {format_size(self.image.size)} "
                    f"in {format_duration(imager.duration)} "
                    f"at {format_speed(self.image.size, imager.duration)}"
                )
                if imager.write_duration:
                    click.echo(
                        f"  Writing {format_size(self.image.size)} "
                        f"in {format_duration(imager.write_duration)} "
                        f"at {format_speed(self.image.size, imager.write_duration)}"
                    )
                if imager.verify_duration:
                    click.echo(
                        f"  Verifying {format_size(self.image.size)} "
                        f"in {format_duration(imager.verify_duration)} "
                        f"at {format_speed(self.image.size, imager.verify_duration)}"
                    )
                return imager.returncode

            click.secho(
                f"Flashing failed with {imager.returncode}.", fg="red", bold=True
            )
            click.echo(imager.stdout)

            return imager.returncode
        finally:
            with Halo(
                text=f"{my_prefix}Unmounting source partition", spinner="line"
            ) as spinner:
                timed_unmount(mountpoint=mountpoint, delay=5)
                spinner.succeed("Unmounted source partition")

        questionary.press_any_key_to_continue().ask()


class HardwareClockStep(Step):

    ident: str = "hwclock"
    name: str = "Set Hardware clock to current time"

    def run(self) -> int:
        time.sleep(0.2)
        return 0


class MountRootFsStep(Step):

    ident: str = "mount-rootfs"
    name: str = "Mount Hotspot root filesystem"

    def run(self) -> int:
        time.sleep(0.2)
        return 0

    def cleanup(self) -> int:
        time.sleep(0.2)
        return 0


class BootOrderStep(Step):

    ident: str = "boot"
    name: str = "Change BOOT_ORDER to NVME / USB / SD"

    def run(self) -> int:
        time.sleep(0.2)
        # boot order + POWER_OFF_ON_HALT=1
        return 0


class ResizePartitionStep(Step):

    ident: str = "resize-data"
    name: str = "Resize Hotspot's third partition"
    no_progress: bool = True

    def run(self) -> int:
        with Halo(
            text=f"{self.prefix} Resizing third partition",
            spinner="line",
        ) as spinner:
            time.sleep(0.2)
            spinner.succeed(f"{self.prefix} Resizing third partition")

        with Halo(
            text=f"{self.prefix} Resizing filesystem",
            spinner="line",
        ) as spinner:
            time.sleep(0.2)
            spinner.succeed(f"{self.prefix} Resizing filesystem")

        return 0


class OffspotYAMLStep(Step):

    ident: str = "offspot"
    name: str = "Update offspot.yaml for runtime configuration"

    def run(self) -> int:
        time.sleep(0.2)
        #   battery charger
        #   country-update
        return 0


class DockerStep(Step):

    ident: str = "docker"
    name: str = "Load OCI images onto Docker"

    def run(self) -> int:
        time.sleep(0.2)
        return 0


class StepsManager:

    STEPS: tuple[type[Step], ...] = (
        HardwareClockStep,
        ImagerStep,
        MountRootFsStep,
        BootOrderStep,
        ResizePartitionStep,
        OffspotYAMLStep,
        DockerStep,
    )

    def __init__(
        self,
        host: ProvisionHost,
        image: ImageFileInfo,
        image_device: Device,
        target_disk: Disk,
    ):
        self.host = host
        self.image = image
        self.image_device = image_device
        self.target_disk = target_disk

        self.steps: dict[str, Step] = {}
        self.step_index = -1

    def get_step(self, ident: str) -> Step:
        if ident in self.steps:
            return self.steps[ident]
        for step_t in self.STEPS:
            if step_t.ident == ident:
                self.steps[ident] = step_t(
                    host=self.host,
                    image=self.image,
                    image_device=self.image_device,
                    target_disk=self.target_disk,
                    step_index=self.step_index,
                    total_steps=len(self.STEPS),
                )
                return self.steps[ident]
        raise KeyError(f"No step for {ident}")

    def __iter__(self) -> Generator[Step, None, None]:
        self.step_index = -1
        for index, step_t in enumerate(self.STEPS):
            self.step_index = index
            yield self.get_step(ident=step_t.ident)

    def cleanup(self) -> int:
        ret = 0
        for step_t in reversed(self.STEPS):
            step = self.steps[step_t.ident]
            try:
                ret += step.cleanup()
            except Exception as exc:
                logger.debug(f"Failed to cleanup {step.ident}")
                logger.exception(exc)
                ret += 1
        return ret


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

    def disabled(disk: Disk) -> str | None:
        if disk.name == image_phy_disk.name:
            return "Source disk of selected image"
        if host.dev.provisionos_disk and disk.name == host.dev.provisionos_disk.name:
            return "ProvisionOS disk"

    target_disk_name: str = questionary.select(
        "Select Target Disk",
        choices=[
            questionary.Choice(
                title=f"{disk!s} ({disk.name})",
                value=key,
                disabled=disabled(disk),
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

    stepmgmt = StepsManager(
        host=host, image=image, image_device=image_device, target_disk=target_disk
    )

    for step in stepmgmt:
        try:
            if step.no_progress:
                step.run()
            else:
                with Halo(
                    text=f"{step.prefix} {step.name}",
                    spinner="line",
                ) as spinner:
                    func = "succeed" if step.run() == 0 else "fail"
                    getattr(spinner, func)(f"{step.prefix} {step.name}")
        except Exception as exc:
            logger.debug(exc)
            logger.exception(exc)
            break

    return CliResult(code=0)
