from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import NamedTuple

import orjson

from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.loop import (
    attach_to_device,
    detach_device,
    get_loopdev,
    is_loopdev_free,
)

try:
    import parted  # pyright: ignore reportMissingImports
except ImportError:
    ...
from attrs import define

from provisioner.context import Context

context = Context.get()
logger = context.logger


def get_supported_filesystems(fpath: Path) -> list[str]:
    """list of filesystems that the kernel supports"""
    filesystems: set[str] = set()
    for line in fpath.read_text().splitlines():
        filesystems.add(line.rsplit(maxsplit=1)[-1])
    return list(filesystems)


ALL_SYSTEM_SUPPORTED_FS = get_supported_filesystems(
    Path.cwd().joinpath("filesystems") if context.fake_pi else Path("/proc/filesystems")
)

SUPPORTED_ROOT_FS = [
    fs
    for fs in ("ext2", "ext3", "ext4", "jfs", "btrfs", "xfs", "reiserfs")
    if fs in ALL_SYSTEM_SUPPORTED_FS
]


class SystemDetails(NamedTuple):
    """Details about an inspected image system"""

    is_linux: bool
    release: str | None
    version: str | None
    variant: str | None
    human: str | None
    is_hotspot: bool
    is_raspi: bool

    @classmethod
    def get_non_linux(cls) -> SystemDetails:
        return cls(
            is_linux=False,
            release=None,
            version=None,
            variant=None,
            human="Unknown",
            is_hotspot=False,
            is_raspi=False,
        )


@define
class AttachedImage:
    fpath: Path
    partition: int
    mountpoint: Path
    diskdev: Path
    partdev: Path


@define(kw_only=True)
class ImageFileInfo:
    fpath: Path
    size: int
    device: str
    relpath: Path
    has_mbr: bool
    has_gpt: bool
    has_root: bool
    linux: SystemDetails

    @property
    def name(self) -> str:
        if not self.linux:
            name = "Unknown"
            if self.has_boot:
                name += f" with {'GPT' if self.has_gpt else 'MBR'}"
            if self.has_root:
                name += " with partition(s)"
            return name
        if self.is_hotspot:
            return f"Kiwix Hotspot “{self.linux.variant}” version {self.version}"
        if self.is_raspi:
            return f"Raspberry Pi OS version {self.linux.version}"
        name = self.linux.release or "Unknown"
        if self.linux.variant:
            name += f" {self.linux.variant}"
        if self.linux.version:
            name += " {self.linux.version}"
        return name

    @property
    def path_root(self) -> str:
        return re.sub(r"^.$", "", str(self.relpath.parent)) + os.sep

    @property
    def human(self) -> str:
        return self.linux.human or self.name

    @property
    def kind(self) -> str:
        for prop in ("hotspot", "raspi", "linux"):
            if getattr(self, f"is_{prop}"):
                return prop
        return "other"

    @property
    def version(self) -> str:
        return self.linux.version or "0.0"

    @property
    def has_boot(self) -> bool:
        return self.has_mbr or self.has_gpt

    @property
    def is_compatible(self) -> bool:
        return self.has_root

    @property
    def is_linux(self) -> bool:
        return self.linux.is_linux

    @property
    def is_raspi(self) -> bool:
        return self.linux.is_raspi

    @property
    def is_hotspot(self) -> bool:
        return self.linux.is_hotspot

    @classmethod
    def load(cls, fpath: Path, device: str, relpath: Path) -> ImageFileInfo:
        has_mbr = has_gpt = has_root = False
        linux_info = SystemDetails.get_non_linux()
        try:
            pdevice = parted.getDevice(str(fpath))
            pdisk = parted.newDisk(pdevice)
            if pdisk.type == "gpt":
                has_gpt = True
            elif pdisk.type == "msdos":
                has_mbr = True

            root_parts = [
                part
                for part in pdisk.partitions
                if part.fileSystem.type in SUPPORTED_ROOT_FS
            ]
            if root_parts:
                has_root = True

                attached_img = attach_image(fpath=fpath, partition=root_parts[0].number)
                logger.debug(attached_img)
                linux_info = get_linux_info(mountpoint=attached_img.mountpoint)
                logger.debug(linux_info)
                detach_image(attached_img)

        except Exception as exc:
            logger.error(f"PARTED ERR: {exc}")
            logger.exception(exc)
            ...

        return ImageFileInfo(
            fpath=fpath,
            device=device,
            relpath=relpath,
            size=fpath.stat().st_size,
            has_mbr=has_mbr,
            has_gpt=has_gpt,
            has_root=has_root,
            linux=linux_info,
        )


def parse_envfile(text: str) -> dict[str, str]:
    """dict of key-value paris ENV file content"""
    env_re = re.compile(
        r"""^(?P<key>[^=]+)\s+?=\s+?(?:[\s"']*)(?P<value>.+?)(?:[\s"']*)$"""
    )
    result: dict[str, str] = {}
    for line in text.splitlines():
        if match := env_re.match(line):
            result[match.groupdict()["key"]] = result[match.groupdict()["value"]]
    return result


def get_linux_info(mountpoint: Path) -> SystemDetails:
    """reads a mountpoint as if rootfs to check for system identification"""

    def get_file(fname: str) -> Path:
        return mountpoint.joinpath("etc").joinpath(fname)

    offspot = get_file("offspot.json")
    if offspot.exists():
        try:
            data = orjson.loads(offspot.read_text())
            if data.get("name"):
                return SystemDetails(
                    is_linux=True,
                    release=data["name"],
                    version=data.get("version"),
                    variant=data.get("variant"),
                    human=data.get("human"),
                    is_raspi=True,
                    is_hotspot=True,
                )
        except Exception:
            ...

    ### DEBUG until we have released Hotspot images with offspot.json
    offspot_base = get_file("hostname")
    if offspot_base.exists():
        try:
            data = offspot_base.read_text()
            if data == "offspot-base":
                return SystemDetails(
                    is_linux=True,
                    release="Kiwix Hotspot",
                    version=datetime.datetime.fromtimestamp(
                        offspot_base.stat().st_ctime, tz=datetime.UTC
                    ).strftime("%Y-%m"),
                    variant="Unknown",
                    human=None,
                    is_raspi=True,
                    is_hotspot=True,
                )
        except Exception:
            ...
    ### END

    is_raspi = False
    rpi = get_file("rpi-issue")
    if rpi.exists():
        try:
            data = rpi.read_text().splitlines()[0]
            if "Raspberry Pi" in data:
                is_raspi = True
            if match := re.match(
                r"Raspberry Pi reference (?P<version>\d{4}-\d{2}-\d{2})", data
            ):
                return SystemDetails(
                    is_linux=True,
                    release="Raspberry Pi OS",
                    version=match.groupdict()["version"],
                    variant=None,
                    human=None,
                    is_hotspot=False,
                    is_raspi=True,
                )

        except Exception:
            ...

    lsb_release = get_file("lsb_release")
    if lsb_release.exists():
        try:
            data = parse_envfile(lsb_release.read_text())
            if data.get("DISTRIB_ID"):
                return SystemDetails(
                    is_linux=True,
                    release=data["DISTRIB_ID"],
                    version=data.get("DISTRIB_RELEASE"),
                    variant=data.get("DISTRIB_CODENAME"),
                    human=data.get("DISTRIB_DESCRIPTION"),
                    is_hotspot=False,
                    is_raspi=is_raspi,
                )
        except Exception:
            ...

    os_release = get_file("os_release")
    if os_release.exists():
        try:
            data = parse_envfile(os_release.read_text())
            if data.get("NAME"):
                return SystemDetails(
                    is_linux=True,
                    release=data["NAME"],
                    version=data.get("VERSION_ID"),
                    variant=data.get("VERSION_CODENAME"),
                    human=data.get("PRETTY_NAME"),
                    is_hotspot=False,
                    is_raspi=is_raspi,
                )
        except Exception:
            ...

    for fname in ("issue.net", "issue"):
        file = get_file(fname)
        if file.exists():
            try:
                data = file.read_text().splitlines()[0].strip()
                if data:
                    return SystemDetails(
                        is_linux=True,
                        release=data,
                        version=None,
                        variant=None,
                        human=data,
                        is_hotspot=False,
                        is_raspi=is_raspi,
                    )
            except Exception:
                ...

    return SystemDetails(
        is_linux=False,
        release="Unknown",
        version=None,
        variant=None,
        human=None,
        is_hotspot=False,
        is_raspi=is_raspi,
    )


def attach_image(fpath: Path, partition: int) -> AttachedImage:
    logger.debug(f"attaching {fpath} P{partition}")
    diskdev = Path(get_loopdev())
    logger.debug(f">using {diskdev}")
    if not is_loopdev_free(str(diskdev)):
        raise OSError("loop device {diskdev!s} is not free")
    logger.debug(f">losetup {diskdev} {fpath}")
    attach_to_device(img_fpath=fpath, loop_dev=str(diskdev))
    partdev = Path(f"{diskdev}p{partition!s}")
    mountpoint = mount_to_temp(partdev)
    return AttachedImage(
        fpath=fpath,
        partition=partition,
        mountpoint=mountpoint,
        diskdev=diskdev,
        partdev=partdev,
    )


def detach_image(image: AttachedImage):
    logger.debug(f"detaching {image}")
    unmount(image.mountpoint)
    # detach_device(loop_dev=str(image.partdev), failsafe=False)
    detach_device(loop_dev=str(image.diskdev), failsafe=False)
    image.mountpoint.rmdir()
