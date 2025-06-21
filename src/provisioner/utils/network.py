from __future__ import annotations

import re
import socket
from http import HTTPStatus
from ipaddress import IPv4Address
from subprocess import CompletedProcess

import pycountry
import requests
from attrs import define
from nmcli import device as nmdevice

from provisioner.context import Context
from provisioner.utils.misc import run_command

context = Context.get()
logger = context.logger


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

    def query(self) -> None:
        self.ifaces = get_interfaces()
        self.internet = InternetCheckResult.load()
        self.regdomain = RegDomain.load()
