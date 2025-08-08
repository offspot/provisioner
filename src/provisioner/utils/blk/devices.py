from __future__ import annotations

import enum
from pathlib import Path

from attrs import define, field

from provisioner.context import Context
from provisioner.utils.misc import format_size

context = Context.get()
logger = context.logger


class DeviceType(enum.StrEnum):
    disk = "disk"
    part = "part"


@define(kw_only=True)
class Device:
    name: str
    major: int
    minor: int
    removable: bool
    size: int
    read_only: bool
    type: DeviceType
    mountpoints: list[Path]
    parent: Device | None

    model: str | None = field(default=None)
    fstype: str | None
    fs_size: int
    hotplug: bool
    label: str
    parttypename: str
    partlabel: str
    partuuid: str
    path: Path
    pttype: str
    tran: str
    uuid: str
    vendor: str
    sector_size: int
    state: str

    def __init__(self, **kwargs):  # pyright: ignore
        filtered = {}
        for attr in getattr(self, "__attrs_attrs__", []):
            filtered[attr.name] = kwargs.get(attr.name)  # pyright: ignore
        self.__attrs_init__(**filtered)  # pyright: ignore

    @property
    def partnum(self) -> int:
        # each `sd` device (major) is assigned 16 slots for partitions.
        # not sure how that plays if a disk has more than 16 parts
        # but let's assume we wont encounter this
        # other drivers starts at 0 so it's safe as well
        return self.minor % 16

    @property
    def brand(self) -> str:
        parts = [p for p in [self.vendor, self.model] if p and p.strip()]
        return " ".join(parts or ["Unknown"])

    @property
    def size_human(self) -> str:
        return format_size(self.size, binary=False)

    @property
    def transport(self) -> str:
        return self.tran.upper()

    @property
    def is_mounted(self) -> bool:
        return bool(self.mountpoints)

    @property
    def mountpoint(self) -> Path | None:
        return self.mountpoints[0] if self.is_mounted else None

    @property
    def is_root(self) -> bool:
        return self.mountpoint is not None and self.mountpoint == self.mountpoint.parent

    @property
    def is_exfat(self) -> bool:
        return self.fstype == "exfat"


@define(kw_only=True, auto_attribs=True, auto_detect=True)
class Partition(Device):
    disk: Disk

    def __str__(self) -> str:
        return f"Partition {self.partnum} ({self.size_human}) of {self.disk!s}"

    def __repr__(self) -> str:
        return f"[{self.disk!r}#{self.partnum}]"


@define(kw_only=True, auto_attribs=True, auto_detect=True)
class Disk(Device):
    partitions: list[Partition] = field(kw_only=True, factory=list[Partition])

    def __str__(self) -> str:
        return f"{self.transport} Disk {self.brand} {self.size_human}"

    def __repr__(self) -> str:
        parts = [self.transport, self.vendor, self.size_human]
        return " ".join([item for item in parts if item])

    def add_part(self, partition: Partition):
        self.partitions.append(partition)
