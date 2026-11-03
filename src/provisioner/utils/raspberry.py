import re
import shutil
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Self

import attrs.validators
import orjson
from attrs import define, field

from provisioner.constants import BOOT_ORDER
from provisioner.context import Context
from provisioner.utils.misc import run_command, run_step_command

context = Context.get()
logger = context.logger


DEVICETREE_PATH = (
    Path.cwd() / "devicetree"
    if context.fake_pi
    else Path("/sys/firmware/devicetree/base/")
)
BOOTORDER_RE = re.compile(
    r"^BOOT_ORDER\s*=\s*(?P<value>0X[0-9A-Fa-f]+)\s*$", re.IGNORECASE
)
HDMI_DELAY_RE = re.compile(r"^HDMI_DELAY\s*=\s*(?P<value>[0-1]+)\s*$")
HDMI_DELAY = 0


class BootValue(StrEnum):
    SD_CARD_DETECT = "0"
    SD_CARD = "1"
    NETWORK = "2"
    RPIBOOT = "3"
    USB_MSD = "4"
    BCM_USB_MSD = "5"
    NVME = "6"
    HTTP = "7"
    STOP = "e"
    RESTART = "f"


@define
class BootOrder:
    value: str = field(
        validator=attrs.validators.matches_re(r"^0X[0-9A-Fa-f]+$", re.IGNORECASE)
    )

    @property
    def entries(self) -> list[BootValue]:
        return [BootValue(entry) for entry in reversed(self.value[2:])]

    @property
    def first(self) -> BootValue:
        return self.entries[0]

    def __str__(self) -> str:
        return ", ".join([bv.name for bv in self.entries])

    @classmethod
    def using(cls, args: list[BootValue]) -> "BootOrder":
        return cls("0x" + "".join(reversed([bv.value for bv in args])))


@define
class BootloaderVersion:
    current: int
    latest: int
    connected: bool
    auto_min: int

    @property
    def matches_latest(self) -> bool:
        return self.current >= self.latest

    @property
    def is_uptodate(self) -> bool:
        return self.connected and self.matches_latest

    @property
    def can_update(self) -> bool:
        return not self.matches_latest

    def __str__(self) -> str:
        if self.is_uptodate:
            return f"up-to-date ({self.current:,})"
        if self.matches_latest:
            return f"latest ({self.current:,})"
        return f"outdated {self.current:,} –> {self.latest:,}"  # noqa: RUF001

    @classmethod
    def using(
        cls, args: dict[str, str | int | bool], *, connected: bool
    ) -> "BootloaderVersion":
        return cls(
            current=int(args.get("BOOTLOADER_CURRENT", "0")),
            latest=int(args.get("BOOTLOADER_LATEST", "0")),
            auto_min=int(args.get("BOOTLOADER_AUTO_UPDATE_MIN_VERSION", "0")),
            connected=connected,
        )


def get_serial_number() -> str:
    return DEVICETREE_PATH.joinpath("serial-number").read_text().strip().rstrip("\x00")


def get_model() -> str:
    return DEVICETREE_PATH.joinpath("model").read_text().strip().rstrip("\x00")


def get_bootorder() -> BootOrder:
    ps = run_command(["rpi-eeprom-config"])
    if ps.returncode != 0:
        raise OSError("rpi-eeprom-config failed")
    for line in ps.stdout.splitlines():
        if not line.strip().startswith("BOOT_ORDER"):
            continue
        if match := BOOTORDER_RE.match(line.strip()):
            return BootOrder(value=match.groupdict()["value"])
    raise OSError("rpi-eeprom-config has no BOOT_ORDER!")


def get_new_bootorder_config() -> str:
    """Generated H1 boot-order config for eeprom config update"""
    new_bootorder = BootOrder.using([getattr(BootValue, item) for item in BOOT_ORDER])
    ps = run_step_command(
        [shutil.which("rpi-eeprom-config")], capture_output=True, text=True, check=True
    )
    new_lines = []
    found = {"BOOT_ORDER": False, "HDMI_DELAY": False}
    for line in ps.stdout.splitlines():
        if BOOTORDER_RE.match(line.strip()):
            if found["BOOT_ORDER"]:
                continue
            found["BOOT_ORDER"] = True
            new_lines.append(f"BOOT_ORDER={new_bootorder.value}")
        elif HDMI_DELAY_RE.match(line.strip()):
            if found["HDMI_DELAY"]:
                continue
            found["HDMI_DELAY"] = True
            new_lines.append(f"HDMI_DELAY={HDMI_DELAY!s}")
        elif line:
            new_lines.append(line)
    if not found["BOOT_ORDER"]:
        new_lines.append(f"BOOT_ORDER={new_bootorder.value}")
    if not found["HDMI_DELAY"]:
        new_lines.append(f"HDMI_DELAY={HDMI_DELAY!s}")
    return "\n".join(new_lines)


def update_eeprom(*, verbose: bool = False):
    """flash the “latest” eeprom bin on fs with our boot-order

    This assumes that package rpi-eeprom has been upgraded via APT
    and that RPI_EEPROM_IMMEDIATE_UPDATE=1 default is configured"""

    # ensure we're going to do a direct flash
    if (
        "RPI_EEPROM_IMMEDIATE_UPDATE=1"
        not in Path("/etc/default/rpi-eeprom-update").read_text().splitlines()
    ):
        raise OSError("RPI_EEPROM_IMMEDIATE_UPDATE not configured")

    config = get_new_bootorder_config()
    with tempfile.NamedTemporaryFile(
        prefix="epprom_config_", suffix=".txt", delete=True
    ) as fh:
        config_path = Path(fh.name)
        config_path.write_text(config)
        if verbose:
            logger.info(f"{config_path=}:\n{config_path.read_text()}")
        run_step_command(
            [shutil.which("rpi-eeprom-config"), "--apply", str(config_path)],
            capture_output=True,
            text=True,
            check=True,
        )


class BootConfig(dict):
    """Manager for content of /boot/firmware/config.txt firmware config file"""

    @classmethod
    def parse(cls, text: str) -> Self:
        board_type_re = re.compile(r"^\[board-type=(?P<name>\d+)\]$")
        filter_re = re.compile(r"^\[(?P<name>[a-z0-9\+]+)\]$")
        data = {}
        currrent_filter = ""
        for line in text.splitlines():
            if m := board_type_re.match(line):
                currrent_filter = m.groupdict()["name"]
            elif m := filter_re.match(line):
                currrent_filter = m.groupdict()["name"]
            else:
                if currrent_filter not in data:
                    data[currrent_filter] = []
                data[currrent_filter].append(line)
        return cls(data)

    def remove_key(self, key: str, *, only_in: list[str] | None = None):
        """remove line for this key in every filter or selected ones"""
        for fname, f_lines in self.items():
            if only_in and key not in only_in:
                continue
            for index, line in enumerate(f_lines):
                if line.startswith(f"{key}="):
                    del self[fname][index]

    def add_key(self, key: str, value: str, cfilter: str = "all"):
        if cfilter not in self:
            self[cfilter] = []
        self[cfilter].append(f"{key}={value}")

    def serialize(self) -> str:
        # start with no filter ones (convewntion)
        lines: list[str] = []
        if "" in self:
            lines += self[""]

        for f_name, f_lines in self.items():
            if f_name in ("", "all"):
                continue

            # no need to fill empty filters
            if not f_lines:
                continue
            # add empty line before filter change is there was none
            if lines and lines[-1]:
                lines += [""]

            lines += [f"[{f_name}]", *f_lines]

        # end with the all ones (convention)
        if self.get("all", []):
            if lines and lines[-1]:
                lines += [""]
            lines += ["[all]", *self["all"]]

        return "\n".join([*lines, "\n"])


def get_bootloader_version(*, is_connected: bool) -> BootloaderVersion:
    if is_connected:
        apt = run_command(["apt", "update"])
        if apt.returncode != 0:
            is_connected &= False
    if is_connected:
        apt = run_command(["apt", "install", "-y", "rpi-eeprom"])
        if apt.returncode != 0:
            is_connected &= False

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as fh:
        ps = run_command(["rpi-eeprom-update", "-j", "-m", fh.name])
        # returns 1 on new update available
        if ps.returncode not in (0, 1):
            raise OSError(f"rpi-eeprom-update failed: rc={ps.returncode}")
        payload = orjson.loads(Path(fh.name).read_text())

    if payload.get("EXITCODE") not in ("EXIT_SUCCESS", "EXIT_UPDATE_REQUIRED"):
        raise OSError(f"rpi-eeprom-update failed: {payload.get('EXITCODE')}")

    return BootloaderVersion.using(payload, connected=is_connected)
