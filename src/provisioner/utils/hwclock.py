from pathlib import Path

from attrs import define

from provisioner.context import Context
from provisioner.utils.misc import find_file

context = Context.get()

rtc0_path = (
    Path.cwd().joinpath("rtc0").resolve()
    if context.fake_pi
    else find_file(under=Path("/sys/devices/platform"), named="rtc0")
)


@define
class RTCBatteryCharger:
    charging_voltage: float
    charging_voltage_max: float
    charging_voltage_min: float

    @property
    def is_present(self) -> bool:
        return self.charging_voltage >= 0

    @property
    def enabled(self) -> bool:
        return self.charging_voltage > 0

    @classmethod
    def read_microvolt_sysfile(cls, fname: str) -> float:
        fpath = rtc0_path.joinpath(fname)
        if not fpath.exists():
            return -1.0
        return int(fpath.read_text()) / 1000000

    @classmethod
    def load(cls) -> "RTCBatteryCharger":
        return cls(
            charging_voltage=cls.read_microvolt_sysfile("charging_voltage"),
            charging_voltage_max=cls.read_microvolt_sysfile("charging_voltage_max"),
            charging_voltage_min=cls.read_microvolt_sysfile("charging_voltage_min"),
        )

    def save(self):
        rtc0_path.joinpath("charging_voltage").write_text(
            str(int(self.charging_voltage * 1000000)) if self.charging_voltage else "0"
        )

    @property
    def range_human(self) -> str:
        return (
            f"{self.charging_voltage_min}V"
            f" – {self.charging_voltage_max}V"  # noqa: RUF001
        )

    @property
    def status_human(self) -> str:
        if not self.is_present:
            return "Not found"
        if not self.enabled:
            return f"Disabled (Range {self.range_human})"
        return f"Enabled at {self.charging_voltage}V (Range {self.range_human})"
