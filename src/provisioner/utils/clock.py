import datetime
import os
import subprocess
import zoneinfo

import dateutil.parser
from attrs import define

from provisioner.context import Context
from provisioner.utils.hwclock import RTCBatteryCharger

context = Context.get()

# build list of timezone abbrevations
std = datetime.datetime(2024, 1, 1)  # noqa: DTZ001
dst = datetime.datetime(2024, 6, 1)  # noqa: DTZ001
tz_map = {}
for zone in zoneinfo.available_timezones():
    tz = zoneinfo.ZoneInfo(zone)
    tz_map[tz.tzname(std)] = tz
    tz_map[tz.tzname(dst)] = tz

timedatectl_bin = "timedatectl" if context.fake_pi else "/usr/bin/timedatectl"
two_minutes = 120


@define
class TimedatectlData:
    retcode: int
    raw_output: str
    raw_data: dict[str, str]
    parsed: bool

    timezone: zoneinfo.ZoneInfo
    rtc_in_local_tz: bool
    can_ntp: bool
    ntp_enabled: bool
    ntp_synced: bool
    local_time: datetime.datetime
    has_rtc: bool
    rtc_time: datetime.datetime

    def __init__(self, *, retcode: int, output: str):
        self.retcode = retcode
        self.raw_output = output

        self.raw_data = {}
        for line in self.raw_output.splitlines():
            if not line.strip():
                continue
            parts = line.split("=", 1)
            self.raw_data[parts[0].strip()] = (
                parts[-1].strip() if len(parts) > 1 else ""
            )

        try:
            self.parse()
        except Exception:
            raise
            self.parsed = False
        else:
            self.parsed = True

    @classmethod
    def load(cls):
        os.environ["LANG"] = "C"
        os.environ["LC_ALL"] = "C"
        ps = subprocess.run(
            ["/usr/bin/env", timedatectl_bin, "show"],
            capture_output=True,
            text=True,
            env=os.environ,
            check=False,
        )
        status_code = ps.returncode
        status_output = ps.stdout.strip()
        ps = subprocess.run(
            ["/usr/bin/env", timedatectl_bin, "show-timesync"],
            capture_output=True,
            text=True,
            env=os.environ,
            check=False,
        )
        time_code = ps.returncode
        time_output = ps.stdout.strip()
        return TimedatectlData(
            retcode=status_code + time_code, output=status_output + "\n" + time_output
        )

    def parse(self):
        def parse_date(text: str) -> datetime.datetime:
            return dateutil.parser.parse(text, tzinfos=tz_map, fuzzy=True)

        def parse_tz(text: str) -> zoneinfo.ZoneInfo:
            return zoneinfo.ZoneInfo(text.strip())

        self.timezone = parse_tz(self.raw_data["Timezone"])
        self.rtc_in_local_tz = self.raw_data["LocalRTC"] == "yes"
        self.can_ntp = self.raw_data["CanNTP"] == "yes"
        self.ntp_enabled = self.raw_data["NTP"] == "active"
        self.ntp_synced = self.raw_data["NTPSynchronized"] == "yes"
        self.local_time = parse_date(self.raw_data["TimeUSec"])
        self.has_rtc = "RTCTimeUSec" in self.raw_data
        if self.has_rtc:
            self.rtc_time = parse_date(self.raw_data["RTCTimeUSec"])

    @property
    def failed(self) -> bool:
        return self.retcode != 0

    @property
    def rtc_utc_time(self) -> datetime.datetime:
        if not self.has_rtc:
            raise OSError("No RTC detected")
        return self.rtc_time.astimezone(datetime.UTC)

    @property
    def utc_time(self) -> datetime.datetime:
        return self.local_time.astimezone(datetime.UTC)

    @property
    def sys_and_rtc_synced(self) -> bool:
        if not self.has_rtc:
            return True
        return abs((self.rtc_utc_time - self.utc_time).total_seconds()) <= two_minutes

    @property
    def all_good(self) -> bool:
        return all([self.ntp_enabled, self.ntp_synced, self.sys_and_rtc_synced])

    @property
    def ntp_status_human(self):
        if self.ntp_synced:
            return "Synced"
        if not self.can_ntp:
            return "Not installed"
        if not self.ntp_enabled:
            return "Not enabled"
        return "Not synced"

    @property
    def warnings(self) -> list[str]:
        warnings: list[str] = []
        out_of_sync = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)

        if not self.ntp_enabled:
            warnings.append(
                "NTP Syncing is disabled. That's unexpected. "
                "System clock will not auto sync when online."
            )
        if not self.ntp_synced:
            warnings.append(
                "System time is not synced via NTP. It's normal when offline."
            )
        if self.utc_time <= out_of_sync:
            warnings.append("System time is in the past.")
        if self.has_rtc and self.rtc_time <= out_of_sync:
            warnings.append("RTC time is in the past.")

        return warnings


class ClockManager:

    tdctl: TimedatectlData
    rtc_charger: RTCBatteryCharger

    def __init__(self) -> None: ...

    def query(self):
        self.tdctl = TimedatectlData.load()
        self.rtc_charger = RTCBatteryCharger.load()
