import re
import shutil
import tempfile
from enum import StrEnum
from pathlib import Path

import attrs.validators
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
POWEROFFONHALT_RE = re.compile(r"POWER_OFF_ON_HALT\s*=*(?P<value>[0-1])\s")


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


def update_eeprom(*, verbose: bool = False):
    """update device's EEPROM to apply our BOOT_ORDER and other options"""
    new_bootorder = BootOrder.using([getattr(BootValue, item) for item in BOOT_ORDER])
    ps = run_step_command(
        [shutil.which("rpi-eeprom-config")], capture_output=True, text=True, check=True
    )
    new_lines = []
    for line in ps.stdout.splitlines():
        if BOOTORDER_RE.match(line.strip()):
            new_lines.append(f"BOOT_ORDER={new_bootorder.value}")
        elif POWEROFFONHALT_RE.match(line.strip()):
            new_lines.append("POWER_OFF_ON_HALT=1")
        else:
            new_lines.append(line)
    config_path = Path(
        tempfile.NamedTemporaryFile(
            prefix="epprom_config_", suffix=".txt", delete=False
        ).name
    )
    config_path.write_text("\n".join(new_lines))
    if verbose:
        logger.info(f"{config_path=}:\n{config_path.read_text()}")
    ps = run_step_command(
        [shutil.which("rpi-eeprom-config"), "--apply", str(config_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    config_path.unlink(missing_ok=True)
