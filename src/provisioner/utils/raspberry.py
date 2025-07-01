import re
from enum import StrEnum
from pathlib import Path

import attrs.validators
from attrs import define, field

from provisioner.context import Context
from provisioner.utils.misc import run_command

context = Context.get()


DEVICETREE_PATH = (
    Path.cwd() / "devicetree"
    if context.fake_pi
    else Path("/sys/firmware/devicetree/base/")
)


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
        if match := re.match(
            r"^BOOT_ORDER\s*=\s*(?P<value>0X[0-9A-Fa-f]+)\s*$",
            line.strip(),
            re.IGNORECASE,
        ):
            return BootOrder(value=match.groupdict()["value"])
    raise OSError("rpi-eeprom-config has no BOOT_ORDER!")


def update_eeprom(values: dict[str, str], *, clear: bool = False): ...
