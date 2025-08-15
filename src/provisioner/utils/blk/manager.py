import os
import re
from pathlib import Path
from typing import NamedTuple

from provisioner.context import Context
from provisioner.utils.blk.devices import Device, Disk
from provisioner.utils.blk.lsblk import get_devices, get_disks_from_devices
from provisioner.utils.blk.misc import mount_to_temp, timed_unmount
from provisioner.utils.imgprobe import ImageFileInfo

context = Context.get()
logger = context.logger


class ImageLocation(NamedTuple):
    device: str  # device name (sda1)
    path: Path  # folder path relative to device root
    nb_img: int  # nb of found IMG file in the folder (matching size)
    total_size: int  # sum size of matching IMG file in folder
    has_boot: bool  # whether at least one has a partition sector (MBR/GPT)
    has_release: (
        bool  # whether at least one has a release file on first “root” part (linux)
    )
    has_hotspot: bool  # whether at least one is a Kiwix Hotspot image (issue.json)

    @property
    def path_root(self) -> str:
        return re.sub(r"^.$", "", str(self.path)) + os.sep


class BlockDevicesManager:
    disks: dict[str, Disk]
    images: list[ImageFileInfo]

    def __init__(self) -> None:

        self.disks: dict[str, Disk] = {}
        self.images: list[ImageFileInfo] = []

    @property
    def has_single_target(self) -> bool:
        return len(self.target_disks) == 1

    @property
    def has_at_least_one_target(self) -> bool:
        return len(self.target_disks) >= 1

    @property
    def has_at_least_one_image(self) -> bool:
        return len(self.images) >= 1

    @property
    def has_single_image(self) -> bool:
        return len(self.images) == 1

    def query(self):
        self.disks = get_disks_from_devices(get_devices())
        self.images = self.get_images()

    def get_disk_from_path(self, path: Path) -> Device:
        for disk in self.disks.values():
            if disk.path == path:
                return disk
            for partition in disk.partitions:
                if partition.path == path:
                    return partition
        raise KeyError(f"No device with path: {path}")

    def get_disk_from_name(self, name: str) -> Device:
        for disk in self.disks.values():
            if disk.name == name:
                return disk
            for partition in disk.partitions:
                if partition.name == name:
                    return partition
        raise KeyError(f"No device with name: {name}")

    @property
    def provisionos_disk(self) -> Disk | None:
        for disk in self.disks.values():
            if disk.is_mounted and disk.is_root:
                return disk
            logger.debug(f"{disk} is not mounted nor root")
            for partition in disk.partitions:
                if partition.is_mounted and partition.is_root:
                    return disk
                logger.debug(f"{partition} is not mounted nor root")

    @property
    def source_disks(self) -> list[Disk]:
        source_disks = list(self.disks.values())

        # remove provisionOS disk
        root_disk = self.provisionos_disk
        if root_disk and root_disk in source_disks:
            source_disks.remove(root_disk)

        return list(source_disks)

    def get_images(self) -> list[ImageFileInfo]:
        images: list[ImageFileInfo] = []

        # build list of to-consider devices: exfat disk or partitions
        devices: list[Device] = []
        for disk in self.disks.values():
            if disk.is_exfat:
                devices.append(disk)
            for partition in disk.partitions:
                if partition.is_exfat:
                    devices.append(partition)

        # iterate over those devices (disk or part)
        for device in devices:
            # mount to a temp folder if not already mounted
            if device.is_mounted and device.mountpoint:
                mountpoint = device.mountpoint
                should_unmount = False
            else:
                try:
                    mountpoint = mount_to_temp(device.path)
                except Exception as exc:
                    logger.error(f"Unable to mount {device.name}: {exc}")
                    logger.exception(exc)
                    continue
                should_unmount = True

            # find all *.img files within mountpoint
            # exclude files that are too small
            for fpath in mountpoint.rglob("*.img"):
                if fpath.stat().st_size < context.min_img_size:
                    continue

                try:
                    img_info = ImageFileInfo.load(
                        fpath,
                        device=device.name,
                        relpath=fpath.relative_to(mountpoint),
                    )
                except Exception as exc:
                    logger.error(f"Failed to read {fpath}: {exc}")
                    logger.exception(exc)
                    continue
                else:
                    if img_info.is_compatible:
                        images.append(img_info)

            if should_unmount:
                try:
                    timed_unmount(mountpoint)
                    mountpoint.rmdir()
                except Exception as exc:
                    logger.error(f"Failed to unmount {device.path}: {exc}")
                    logger.exception(exc)
                continue

        class ImageUsefulness:
            """Sorting comparator for ImageFileInfo's usefulness in manager

            - Kind is most important (Hotspot first)
            - Then Version (most recent first)
            - Then filesize (larger first)
            """

            def __init__(self, obj: ImageFileInfo):
                self.image = obj

            @staticmethod
            def get_kind_index(image: ImageFileInfo) -> int:
                rule = ["hotspot", "raspi", "linux", "other"]
                try:
                    return rule.index(image.kind)
                except ValueError:
                    return len(rule) + 1

            def __lt__(self, other: object) -> bool:
                if not isinstance(other, ImageUsefulness):
                    raise NotImplementedError()
                # other: ImageFileInfo = other
                main_self = self.get_kind_index(self.image)
                main_other = self.get_kind_index(other.image)
                if main_self != main_other:
                    return main_self < main_other
                if self.image.version != other.image.version:
                    return self.image.version > other.image.version
                return self.image.size > other.image.size

            def __gt__(self, other: object) -> bool:
                return not self.__lt__(other)

            def __le__(self, other: object) -> bool:
                return self.__eq__(other) or self.__lt__(other)

            def __ge__(self, other: object) -> bool:
                return self.__eq__(other) or self.__gt__(other)

            def __eq__(self, other: object) -> bool:
                if not isinstance(other, ImageUsefulness):
                    return False
                return (
                    self.image.kind == other.image.kind
                    and self.image.version == other.image.version
                    and self.image.size == other.image.size
                )

            def __ne__(self, other: object) -> bool:
                if not isinstance(other, ImageUsefulness):
                    return True
                return not self.__eq__(other)

        return sorted(images, key=ImageUsefulness)

    @property
    def target_disks(self) -> list[Disk]:
        def comp_by_tech_and_size(disk: Disk) -> tuple[int, float]:
            # the tech order we prefer
            rule = ["NVME", "USB", "SD"]
            # we want to sort ascending by larger disks first
            try:
                disk_value = 1 / disk.size
            except ZeroDivisionError:
                import ipdb

                ipdb.set_trace()
            try:
                return (rule.index(disk.transport), disk_value)
            except ValueError:
                return (len(rule) + 1, disk_value)

        target_disks = list(self.disks.values())
        # remove provisionOS disk
        root_disk = self.provisionos_disk
        if root_disk and root_disk in target_disks:
            target_disks.remove(root_disk)
        # remove mounted ones?
        target_disks = filter(lambda disk: not disk.is_mounted, target_disks)
        target_disks = sorted(target_disks, key=comp_by_tech_and_size)

        return list(target_disks)

    @property
    def nvme_target_disks(self) -> list[Disk]:
        return list(filter(lambda disk: disk.transport == "NVME", self.target_disks))

    @property
    def nvme_target_disk(self) -> Disk:
        return self.target_disks[0]

    @property
    def target_disk(self) -> Disk | None:
        return self.target_disks[0] if self.target_disks else None
