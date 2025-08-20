from collections.abc import Callable
from typing import Any

import click
from prettytable import PrettyTable, TableStyle

from provisioner.cli.common import (
    CliResult,
    error_text,
    refresh,
    regular_text,
    success_text,
    warning_text,
)
from provisioner.constants import WL_IFACE
from provisioner.context import Context
from provisioner.host import ProvisionHost
from provisioner.utils.blk.manager import BlockDevicesManager
from provisioner.utils.misc import format_dt, format_size, padding, yesno
from provisioner.utils.network import Interface, InternetCheckResult
from provisioner.utils.raspberry import BootValue

context = Context.get()
logger = context.logger


def get_decor(value: bool) -> Callable[[str], str]:  # noqa: FBT001
    return success_text if value else error_text


def get_warnmiss_decor(value: Any) -> Callable[[str], str]:
    return warning_text if not value else regular_text


def get_ethernet_cell(eth0: Interface) -> str:
    rows: list[str] = []
    status_decor = get_decor(eth0.connected)
    rows.append(status_decor("Connected" if eth0.connected else "Not connected"))
    rows.append(f"IP: {eth0.ip4_address}")
    rows.append(f"GW: {eth0.ip4_gateway}")
    rows.append(f"DNS: {eth0.ip4_dns}")
    rows.append(f"HW: {eth0.hwaddr}")
    return "\n  ".join(rows)


def get_wifi_cell(wlan0: Interface) -> str:
    rows: list[str] = []
    if not wlan0.available:
        status_decor = error_text
    elif wlan0.connected:
        status_decor = success_text
    else:
        status_decor = regular_text

    rows.append(status_decor(wlan0.status))
    rows.append(f"SSID: {wlan0.ssid}")
    rows.append(f"IP: {wlan0.ip4_address}")
    rows.append(f"GW: {wlan0.ip4_gateway}")
    rows.append(f"DNS: {wlan0.ip4_dns}")
    rows.append(f"HW: {wlan0.hwaddr}")
    return "\n  ".join(rows)


def get_internet_cell(internet: InternetCheckResult) -> str:
    rows: list[str] = []
    if internet.https:
        status_decor = success_text
    elif not internet.connect_ip:
        status_decor = error_text
    else:
        status_decor = warning_text
    rows.append(status_decor(internet.status))
    rows.append(f"IP: {internet.public_ip}")
    return "\n  ".join(rows)


def get_images_cell(devmgmt: BlockDevicesManager, *, show_paths: bool = False) -> str:
    rows: list[str] = []
    nb_imgs = len(devmgmt.images)
    total_size = sum([image.size for image in devmgmt.images])
    nb_disks = len({image.device for image in devmgmt.images})
    rows.append(
        f"{nb_imgs} images, totaling {format_size(total_size, binary=False)} "
        f"on {nb_disks} disks"
    )
    for image in devmgmt.images[:10]:
        path_or_name = (
            f"[/dev/{image.device}:/{image.relpath}]"
            if show_paths
            else f"{devmgmt.get_disk_from_name(image.device)!r} "
        )
        rows.append(
            f"{padding(format_size(image.size, binary=False), 10)} "
            f"{padding(image.human, 45, on_end=True)} {path_or_name}"
        )
    return "\n".join(rows)


def get_target_disk_cell(
    devmgmt: BlockDevicesManager, *, show_paths: bool = False
) -> str:
    # target_disk_decor = get_warnmiss_decor(host.dev.target_disk)
    if not devmgmt.target_disk:
        return error_text(str(devmgmt.target_disk))
    elif len(devmgmt.target_disks) == 1:
        value = str(devmgmt.target_disk)
        if show_paths:
            value += f" [{devmgmt.target_disk.path}]"
        return value

    value = f"{devmgmt.target_disk!s}"
    if show_paths:
        value += f" [{devmgmt.target_disk.path}]"
    value += f" (+{len(devmgmt.target_disks) -1} other)"
    return value


def main(host: ProvisionHost, *, show_paths: bool = False) -> CliResult:
    refresh(host)

    table = PrettyTable(align="l", header=False)
    table.set_style(TableStyle.DOUBLE_BORDER)
    table.header = False
    table.add_row(["Host Hardware", click.style(host.model, bold=True)])
    table.add_row(["Host S/N", host.serial_number.upper()])
    boot_order_decor = regular_text
    if not host.boot_order:
        boot_order_decor = error_text
    elif host.boot_order.first != BootValue.NVME:
        boot_order_decor = warning_text
    table.add_row(["Host BOOT Order", boot_order_decor(str(host.boot_order))])
    table.add_divider()
    table.add_row(["Internet", get_internet_cell(host.network.internet)])
    table.add_row(
        [
            "Ethernet",
            get_ethernet_cell(host.network.ifaces["eth0"]),
        ]
    )
    table.add_row(["WiFi", get_wifi_cell(host.network.ifaces[WL_IFACE])])
    wifi_country_decor = get_warnmiss_decor(host.network.regdomain.code)
    table.add_row(
        ["WiFi Country (OS)", wifi_country_decor(str(host.network.regdomain.code))]
    )
    table.add_divider()
    ntp_decor = get_decor(host.clock.tdctl.ntp_synced)
    table.add_row(["NTP", ntp_decor(host.clock.tdctl.ntp_status_human)])
    table.add_row(["Timezone (OS)", host.clock.tdctl.timezone])
    table.add_row(["RTC Clock Found", yesno(host.clock.tdctl.has_rtc)])
    table.add_row(["System Clock (UTC)", format_dt(host.clock.tdctl.utc_time)])
    table.add_row(["RTC Clock (UTC)", format_dt(host.clock.tdctl.rtc_utc_time)])
    charger_decor = (
        error_text if not host.clock.rtc_charger.is_present else regular_text
    )
    table.add_row(
        [
            "RTC Battery Charging (OS)",
            charger_decor(host.clock.rtc_charger.status_human),
        ]
    )
    table.add_divider()
    provision_disk_str = str(host.dev.provisionos_disk)
    if host.dev.provisionos_disk and show_paths:
        provision_disk_str += f" [{host.dev.provisionos_disk.path}]"
    table.add_row(["ProvisionOS Disk", provision_disk_str])

    table.add_row(
        ["Target Disk", get_target_disk_cell(host.dev, show_paths=show_paths)]
    )
    table.add_row(["Images Founds", get_images_cell(host.dev, show_paths=show_paths)])
    click.echo(table.get_string())  # pyright: ignore[reportUnknownMemberType]

    return CliResult(
        code=0,
        payload={"auto_provision": host.provision_ready[0]},
    )

    return 0
