import time
from collections.abc import Callable
from typing import TypeAlias

import click
import questionary
from attrs import define
from halo import Halo
from nmcli import device as nmdevice

from provisioner.cli.common import CliResult
from provisioner.constants import ETH_IFACE, RC_CANCELED, REGULATORY_DOMAINS, WL_IFACE
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.utils.misc import run_command
from provisioner.utils.network import (
    StaticIPConf,
    WiFiNetwork,
    apply_dhcp,
    apply_static,
    validate_ip4,
)

context = Context.get()
logger = context.logger
Entrypoint: TypeAlias = Callable[[], int]


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


def configure_wifi(iface: str = WL_IFACE) -> int:  # noqa: ARG001
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


def main(host: ProvisionHost) -> CliResult:  # noqa: ARG001

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
