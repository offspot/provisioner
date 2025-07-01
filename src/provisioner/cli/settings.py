import math
import time
from collections.abc import Callable
from ipaddress import IPv4Address
from typing import TypeAlias

import click
import questionary
from attrs import define
from halo import Halo
from nmcli import device as nmdevice
from nmcli.data.device import DeviceWifi

from provisioner.cli.common import CliResult, padding
from provisioner.constants import ETH_IFACE, RC_CANCELED, REGULATORY_DOMAINS, WL_IFACE
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.utils.misc import run_command

context = Context.get()
logger = context.logger

# # Changes here are persisting.
# - Configure Ethernet (eth0)
# Do you want DHCP or Static?
#     DHCP
#         done
#     STATIC
#         IP Address Use CIDR for netmask?
#             GW?
#                 DNS?
#                     done
# - Wireless Country (regulation)
# - Configure WiFi (wlan0)
# SSID ? (display list)
#     Passphrase?
#         DHCP or STATIC ?
#             DHCP
#                 done
#             STATIC
#                 IPAddress?
#                     GW?
#                         DNS?
#                             done
# - Timezone
# Pick from list/autocomplete
# - Toggle Telemetry
# - Reset

Entrypoint: TypeAlias = Callable[[], int]


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


def get_static_config() -> StaticIPConf | None:
    ip = questionary.text(
        "IPv4 Address", default="192.168.1.100", validate=validate_ip4
    ).ask()
    if not ip:
        return

    gw = questionary.text(
        "Gateway (router's address)", default="192.168.1.1", validate=validate_ip4
    ).ask()
    if not gw:
        return

    dns = questionary.text(
        "DNS Address", default="192.168.1.1", validate=validate_ip4
    ).ask()

    if not dns:
        return

    return StaticIPConf(address=ip, gateway=gw, dns=dns)


def configure_ethernet(iface: str = ETH_IFACE) -> int:
    selected_type = questionary.select(
        "Addressing?",
        choices=[
            questionary.Choice(title="DHCP", value="dhcp"),
            questionary.Choice(title="Static IP", value="static"),
        ],
        use_shortcuts=True,
        default="dhcp",
    ).ask()
    if not selected_type:
        return RC_CANCELED

    if selected_type == "dhcp":
        with Halo(
            text=f"Applying DHCP configuration to {iface}", spinner="dots"
        ) as spinner:
            res = apply_dhcp(iface=iface)
            if res.success:
                spinner.succeed(res.text)
            else:
                spinner.fail(res.text)
        return 0
    else:
        conf = get_static_config()
        if conf is None:
            return RC_CANCELED
        with Halo(
            text=f"Applying Static configuration ({conf.address}) to {iface}",
            spinner="dots",
        ) as spinner:
            res = apply_static(iface=iface, static=conf)
            if res.success:
                spinner.succeed(res.text)
            else:
                spinner.fail(res.text)

    return 0


def configure_addressing(iface: str):
    selected_type = questionary.select(
        "Select Addressing method for {iface}",
        choices=[
            questionary.Choice(title="DHCP", value="dhcp"),
            questionary.Choice(title="Static IP", value="static"),
        ],
        use_shortcuts=True,
        default="dhcp",
    ).ask()
    if not selected_type:
        return RC_CANCELED

    if selected_type == "dhcp":
        with Halo(
            text=f"Applying DHCP configuration to {iface}", spinner="dots"
        ) as spinner:
            res = apply_dhcp(iface=iface)
            if res.success:
                spinner.succeed(res.text)
            else:
                spinner.fail(res.text)
        return 0
    else:
        conf = get_static_config()
        if conf is None:
            return RC_CANCELED
        with Halo(
            text=f"Applying Static configuration ({conf.address}) to {iface}",
            spinner="dots",
        ) as spinner:
            res = apply_static(iface=iface, static=conf)
            if res.success:
                spinner.succeed(res.text)
            else:
                spinner.fail(res.text)


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


def configure_wifi(iface: str = WL_IFACE) -> int:
    enter_choice = questionary.Choice(title="Enter SSID manually", value=":manual:")
    cancel_choice = questionary.Choice(title="Cancel", value="cancel")
    with Halo(text="Finding WiFi networks", spinner="dots"):
        networks = {dev.bssid: WiFiNetwork(dev) for dev in nmdevice.wifi()}

    wifi_signal_styles = questionary.Style(
        [
            ("excelent-signal", "fg:green"),
            ("great-signal", "fg:green"),
            ("correct-signal", "fg:yellow"),
            ("poor-signal", "fg:red"),
            ("bad-signal", "fg:red"),
        ]
    )
    ssid = questionary.select(
        "Select WiFi network",
        choices=[
            questionary.Choice(
                title=[(f"class:{net.signal_code}-signal", str(net))],
                value=net.ident,
            )
            for net in networks.values()
        ]
        + [questionary.Separator(), enter_choice, cancel_choice],
        use_search_filter=True,
        use_jk_keys=False,
        # use_shortcuts=True,
        style=wifi_signal_styles,
    ).ask()
    if not ssid or ssid == cancel_choice.value:
        return RC_CANCELED
    if ssid == enter_choice.value:
        ssid = questionary.text("Enter SSID").ask()
        if not ssid:
            return RC_CANCELED

    passphrase = questionary.text(f"{ssid}'s Passphrase").ask()
    if not passphrase:
        return RC_CANCELED

    nmdevice.wifi_connect(ssid=ssid, password=passphrase)
    time.sleep(3)
    # connect_wifi(ifname=iface, ssid=ssid, passphrase=passphrase)

    configure_addressing(WL_IFACE)
    return 0


def configure_regulatory_domain() -> int:
    domain = questionary.select(
        "Select Country to apply wireless regulations for",
        choices=[
            questionary.Choice(title=name, value=code)
            for code, name in REGULATORY_DOMAINS.items()
        ],
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if not domain:
        return RC_CANCELED
    with Halo(
        text=f"Setting regulatory domain to {domain}",
        spinner="dots",
    ) as spinner:
        res = run_command(["iw", "reg", "set", domain])
        if res.returncode == 0:
            spinner.succeed(res.stdout)
        else:
            spinner.fail(res.stdout)
    return 0


def blank() -> int:
    click.echo("blank")
    return 0


@define
class Setting:
    name: str
    entrypoint: Entrypoint

    def get_choice(self, key: str | None) -> questionary.Choice:
        return questionary.Choice(title=self.name, value=key or self.name)


def main(host: ProvisionHost) -> CliResult:

    click.secho(
        r"/!\ Settings are stored on the ProvisionOS and are thus persistent.",
        fg="yellow",
    )

    entries: dict[str, Setting] = {
        "ethernet": Setting(
            name=f"Configure Ethernet ({ETH_IFACE})", entrypoint=configure_ethernet
        ),
        "wireless_code": Setting(
            name="Change Wireless Country (regulation)",
            entrypoint=configure_regulatory_domain,
        ),
        "wifi": Setting(name=f"Configure WiFi ({WL_IFACE})", entrypoint=configure_wifi),
        "timezone": Setting(name="Change Timezone", entrypoint=blank),
        "telemetry": Setting(name="Configure Telemetry", entrypoint=blank),
        "reset": Setting(name="Reset Settings", entrypoint=blank),
        "exit": Setting(name="Exit Settings", entrypoint=blank),
    }

    while True:
        action = questionary.select(
            "Pick an action",
            choices=[entry.get_choice(key) for key, entry in entries.items()],
            use_shortcuts=True,
        ).ask()
        if not action:
            continue

        if action == "exit":
            return CliResult(code=0)

        try:
            res: int = entries[action].entrypoint()
        except Exception as exc:
            click.secho(
                "Setting crashed. That's unexpected. "
                "Check its output and reboot.\n"
                "If it happens again, take a picture and contact Kiwix."
            )
            ...
            click.echo(exc)
            logger.exception(exc)
            return CliResult(code=-1)

        return CliResult(code=res)
