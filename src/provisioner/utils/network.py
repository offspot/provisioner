from __future__ import annotations

import enum
import math
import re
import socket
from http import HTTPStatus
from ipaddress import IPv4Address
from subprocess import CompletedProcess

import pycountry
import requests
from attrs import define
from nmcli import device as nmdevice
from nmcli.data.device import DeviceWifi

from provisioner.constants import ETH_IFACE, WL_IFACE
from provisioner.context import Context
from provisioner.utils.misc import padding, run_command

context = Context.get()
logger = context.logger


class ConnectedTo(enum.StrEnum):
    none = "Not connected"
    ethernet = "Wired"
    wireless = "Wireless"
    both = "Wired and Wireless"


@define
class WiFiAccessConf:
    ssid: str
    passphrase: str | None


@define
class StaticIPConf:
    address: IPv4Address
    gateway: IPv4Address
    dns: IPv4Address


@define
class Feedback:
    success: bool
    text: str = ""


@define
class WiFiNetwork:
    dev: DeviceWifi

    @property
    def ident(self) -> str:
        return self.bssid

    @property
    def connected(self) -> bool:
        return self.dev.in_use

    @property
    def ssid(self) -> str:
        return self.dev.ssid

    @property
    def bssid(self) -> str:
        return self.dev.bssid

    @property
    def signal(self) -> int:
        return self.dev.signal

    @property
    def signal_symbol(self) -> str:
        symbols = ["▁", "▃", "▄", "▅", "▆"]
        step = self.signal // (100 // len(symbols))
        return padding("".join(symbols[:step]), len(symbols), on_end=True)

    @property
    def signal_code(self) -> str:
        if self.signal >= 90:
            return "excelent"
        if self.signal >= 80:
            return "great"
        if self.signal >= 70:
            return "correct"
        if self.signal >= 50:
            return "poor"
        return "bad"

    @property
    def rate(self) -> int:
        return self.dev.rate

    @property
    def speed(self) -> str:
        return f"{self.rate}Mbps"

    @property
    def security(self):
        return self.dev.security or "Open"

    @property
    def name(self) -> str:
        return self.dev.ssid or f"Hidden ({self.dev.bssid})"

    @property
    def freq(self) -> str:
        nb_giga = math.floor(self.dev.freq / 1000)
        giga = {2: "2.4"}.get(nb_giga, str(nb_giga))
        return f"{giga}Ghz"

    def __str__(self) -> str:
        connected = " (Connected)" if self.connected else ""
        return (
            f"{self.signal_symbol} {self.name}{connected} – "  # noqa: RUF001
            f"{self.security} ({self.freq})"
        )


def apply_dhcp(iface: str) -> Feedback:
    ps = run_command(
        [
            "nmcli",
            "device",
            "modify",
            iface,
            "ipv4.address",
            "",
            "ipv4.gateway",
            "",
            "ipv4.dns",
            "",
            "ipv4.method",
            "auto",
        ]
    )
    return Feedback(success=ps.returncode == 0, text=ps.stdout)


def apply_static(iface: str, static: StaticIPConf) -> Feedback:
    ps = run_command(
        [
            "nmcli",
            "device",
            "modify",
            iface,
            "ipv4.address",
            str(static.address),
            "ipv4.gateway",
            str(static.gateway),
            "ipv4.dns",
            str(static.dns),
            "ipv4.method",
            "auto",
        ]
    )
    return Feedback(success=ps.returncode == 0, text=ps.stdout.splitlines()[-1])


def validate_ip4(value: str) -> bool:
    try:
        ip = IPv4Address(value)
        return not ip.is_loopback and not ip.is_multicast
    except Exception:
        return False


@define(kw_only=True)
class RegDomain:
    code: str | None

    @classmethod
    def load(cls) -> RegDomain:
        code = None
        ps = run_command(["iw", "reg", "get"])
        if ps.returncode:
            return RegDomain(code=code)
        for line in ps.stdout.strip().splitlines():
            if m := re.match(r"^country (?P<code>[0-9A-Z]+): (.+)$", line):
                return RegDomain(code=m.groupdict().get("code") or code)
        return RegDomain(code=code)


@define(kw_only=True)
class InternetCheckResult:

    connect_ip: bool
    http: bool
    https: bool
    public_ip: str | None

    @classmethod
    def load(cls) -> InternetCheckResult:
        connect_ip = http = https = False
        public_ip = None
        # chain tests as a failing one sorta implies next will fail
        if connect_ip := cls.test_ip4():
            if http := cls.test_http():
                if https := cls.test_https():
                    public_ip = cls.get_public_ip()

        return cls(
            connect_ip=connect_ip,
            http=http,
            https=https,
            public_ip=public_ip,
        )

    @property
    def status(self) -> str:
        if self.https:
            return "Connected"
        elif self.http:
            return "Connected (SSL not working)"
        elif self.connect_ip:
            return "Connected (HTTP/s not working)"
        return "Not connected"

    @staticmethod
    def test_ip4(host: str = "1.1.1.1") -> bool:
        try:
            socket.create_connection((host, 53), timeout=8)
            return True
        except Exception:
            ...
        return False

    @staticmethod
    def test_http(url: str = "http://wikipedia.org") -> bool:
        try:
            return (
                requests.get(url, timeout=8, allow_redirects=True).status_code
                == HTTPStatus.OK
            )
        except Exception:
            return False

    @staticmethod
    def test_https(url: str = "https://wikipedia.org") -> bool:
        try:
            return (
                requests.get(url, timeout=8, allow_redirects=True).status_code
                == HTTPStatus.OK
            )
        except Exception:
            return False

    @staticmethod
    def get_public_ip(url: str = "http://ipinfo.io") -> str | None:
        try:
            resp = requests.get(
                url,
                timeout=8,
                allow_redirects=True,
                headers={"User-Agent": "curl/8.7.1"},
            )
            if resp.status_code == HTTPStatus.OK:
                payload = resp.json()
                ip = payload.get("ip")
                hostname = payload.get("hostname")
                city = payload.get("city")
                region = payload.get("region")
                country_code = payload.get("country")
                try:
                    country = pycountry.countries.get(alpha_2=country_code)
                    assert country  # noqa: S101
                    country_name = country.name
                except Exception:
                    country_name = None
                return f"{hostname or ip} ({city or region}, {country_name})"
        except Exception:
            ...


@define(kw_only=True)
class Interface:
    name: str
    type: str
    hwaddr: str
    state: str
    connection: str
    ip4_address: IPv4Address | None
    ip4_gateway: IPv4Address | None
    ip4_dns: IPv4Address | None

    @property
    def status(self) -> str:
        return re.sub(r"\d+\s\((.+)\)$", r"\1", self.state).capitalize()

    @property
    def available(self) -> bool:
        return not self.state.startswith("20 ")

    @property
    def connected(self) -> bool:
        return self.state.startswith("100 ")

    @property
    def ssid(self) -> str:
        return self.connection


def connect_wifi(
    ifname: str,
    *,
    ssid: str,
    passphrase: str | None,
    rescan: bool = False,  # noqa: ARG001
) -> CompletedProcess[str]:
    args = ["nmcli", "device", "wifi", "connect", ssid]
    if passphrase:
        args += ["password", str(passphrase)]
    args += ["ifname", ifname]
    return run_command(args)


def disconnect_wifi(device: Interface) -> CompletedProcess[str]:
    if device.connection:
        run_command(["nmcli", "connection", "delete", "id", device.connection])
    return run_command(["nmcli", "device", "disconnect", device.name])


def get_interfaces() -> dict[str, Interface]:
    ifaces: list[Interface] = []
    for ifr in nmdevice.show_all():

        ifaces.append(
            Interface(
                name=ifr["GENERAL.DEVICE"],
                type=ifr["GENERAL.TYPE"],
                hwaddr=ifr["GENERAL.HWADDR"],
                state=ifr["GENERAL.STATE"],
                connection=ifr["GENERAL.CONNECTION"],
                ip4_address=(
                    IPv4Address(ifr["IP4.ADDRESS[1]"].split("/")[0])
                    if ifr.get("IP4.ADDRESS[1]")
                    else None
                ),
                ip4_gateway=(
                    IPv4Address(ifr["IP4.GATEWAY"]) if ifr.get("IP4.GATEWAY") else None
                ),
                ip4_dns=(
                    IPv4Address(ifr["IP4.DNS[1]"].split()[0])
                    if ifr.get("IP4.DNS[1]")
                    else None
                ),
            )
        )
    return {iface.name: iface for iface in ifaces}


class NetworkManager:
    ifaces: dict[str, Interface]
    internet: InternetCheckResult

    def __init__(self) -> None: ...

    @property
    def connected_to(self) -> ConnectedTo:
        if self.ifaces[ETH_IFACE].connected and self.ifaces[WL_IFACE].connected:
            return ConnectedTo.both
        elif self.ifaces[ETH_IFACE].connected:
            return ConnectedTo.ethernet
        elif self.ifaces[WL_IFACE].connected:
            return ConnectedTo.wireless
        return ConnectedTo.none

    @property
    def all_good(self) -> bool:
        return (
            self.internet.https
            and not self.is_not_connected
            and not self.is_multi_connected
        )

    @property
    def is_multi_connected(self) -> bool:
        return self.connected_to == ConnectedTo.both

    @property
    def is_not_connected(self) -> bool:
        return self.connected_to == ConnectedTo.none

    def query(self) -> None:
        self.ifaces = get_interfaces()
        self.internet = InternetCheckResult.load()
        self.regdomain = RegDomain.load()
