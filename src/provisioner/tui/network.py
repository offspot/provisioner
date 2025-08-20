import functools
import time
from collections.abc import Hashable
from threading import Thread
from typing import ClassVar

import urwid as uw
from nmcli import connection as nmconn
from nmcli import device as nmdevice

from provisioner.constants import ETH_IFACE, WL_IFACE
from provisioner.tui.pane import Pane
from provisioner.tui.spinner import SpinnerText
from provisioner.utils.misc import run_step_command
from provisioner.utils.network import WiFiNetwork, apply_dhcp


def text_for(net: WiFiNetwork) -> list[str | tuple[Hashable, str]]:
    connected = "[Connected] " if net.connected else ""
    return [
        (f"{net.signal_code}-signal", f"{net.signal_symbol} "),
        f"{connected}{net.name} – "  # noqa: RUF001
        f"{net.security} ({net.freq})",
    ]


class DoneEdit(uw.Edit):
    _metaclass_ = uw.signals.MetaSignals
    signals: ClassVar = ["done"]

    def keypress(self, size, key):
        if key == "enter":
            uw.emit_signal(self, "done", self, self.get_edit_text())
            super().set_edit_text("")
            return
        elif key == "esc":
            super().set_edit_text("")
            return
        uw.Edit.keypress(self, size, key)


class NetworkPane(Pane):

    @property
    def std_option(self):
        return (uw.WHSettings.WEIGHT, 10)

    def reset(self):
        self.app.switch_to("network")

    def render(self):
        # paint solid background with vertical stack
        self.main_widget = uw.Filler(uw.Pile([], focus_item=1), valign="top")
        pile = self.pile

        # paint a text line surrounded by two lines of decor
        div = self.a_divider
        outside = uw.AttrMap(div, "outside")
        inside = uw.AttrMap(div, "inside")
        streak = uw.AttrMap(
            uw.Text("Configure networking", align=uw.Align.CENTER), "streak"
        )
        for item in [outside, inside, streak, inside, outside, self.a_divider]:
            self.append_to(pile, item)

        self.update()
        # re-query network to get an accurate, up-to-date status
        self.host.query_network()

        self.statuses_entry = self.append_to(
            pile,
            uw.Padding(
                self.get_statuses(),
                align=uw.Align.CENTER,
                width=(uw.WHSettings.RELATIVE, 50),
                min_width=50,
            ),
        )

        self.loading_text = SpinnerText(
            "Looking for wireless networks…", align="center"
        )
        self.menu = uw.Pile(
            [
                (
                    *self.std_option,
                    uw.Button("Cancel and go back", on_press=self.on_cancel),
                ),
                (*self.std_option, self.loading_text),
            ]
        )
        decorated_menu = uw.Padding(
            self.menu,
            align=uw.Align.CENTER,
            width=(uw.WHSettings.RELATIVE, 50),
            min_width=50,
        )
        self.append_to(pile, decorated_menu)
        pile.focus_item = decorated_menu

        # request spinner text to animate
        self.loading_text.animate(self.uloop)

        self.update()

        # start thread gathering infos from host
        Thread(target=self.gather_infos).start()

    def get_statuses(self) -> uw.Pile:
        internet = self.host.network.internet
        internet_text = [
            "Internet: ",
            (
                "success-status" if internet.https else "error-status",
                internet.status,
            ),
        ]
        if internet.public_ip:
            internet_text += [f" – IP: {internet.public_ip}"]  # noqa: RUF001

        eth0 = self.host.network.ifaces[ETH_IFACE]
        wlan0 = self.host.network.ifaces[WL_IFACE]
        connected_text: list[str | tuple[Hashable, str]] = []
        if eth0.connected and wlan0.connected:
            connected_text += [
                "🚫 Both Ethernet and WiFi are connected. ",
                "This is unreliable. ",
                "Please configure one",
            ]
        elif eth0:
            connected_text += [
                "✅ Connected via Ethernet (wired) –"  # noqa: RUF001
                f" IP: {eth0.ip4_address}"
            ]
        elif wlan0:
            connected_text += [
                "✅ Connected via WiFi “{wlan0.name}” –"  # noqa: RUF001
                f" IP: {eth0.ip4_address}"
            ]
        else:
            connected_text += [
                "🚫 Neither Ethernet nor WiFi connected. Please configure one"
            ]

        pile = uw.Pile(
            [
                uw.Text(internet_text, align=uw.Align.LEFT),
                uw.Text(connected_text, align=uw.Align.LEFT),
                uw.Divider(),
            ]
        )
        return pile

    def remove_statuses(self):
        self.remove_from(self.pile, self.statuses_entry)

    def add_to_menu(self, entry):
        self.menu.contents.append(entry)

    def gather_infos(self):
        # TODO: check if WiFI is blocked.
        # if so, unblock and requery network
        eth0 = self.host.network.ifaces[ETH_IFACE]
        wlan0 = self.host.network.ifaces[WL_IFACE]
        if not wlan0.available:
            run_step_command(["rfkill", "unblock", "wifi"], check=True)
            run_step_command(["iw", "reg", "set", "FR"], check=True)
            run_step_command(["nmcli", "radio", "wifi", "on"], check=True)
            # make sure interface is ready to scan
            time.sleep(3)

        wifi_conf = nmdevice.wifi(ifname=WL_IFACE, rescan=True)
        # when connected, if usually returns just the connected network
        if len(wifi_conf) and wifi_conf[0].in_use:
            nmdevice.disconnect(ifname=WL_IFACE)
            wifi_conf = nmdevice.wifi(ifname=WL_IFACE, rescan=True)
            nmdevice.connect(ifname=WL_IFACE)

        self.networks = {dev.bssid: WiFiNetwork(dev) for dev in wifi_conf}
        self.loading_text.done("")
        # self.menu.contents.pop()

        self.add_to_menu(
            (
                uw.Text("Please choose a networking method:", align=uw.Align.CENTER),
                self.std_option,
            )
        )
        self.add_to_menu((uw.Divider(), self.std_option))
        self.add_to_menu(
            (uw.Text(f"Wired connection (HW: {eth0.hwaddr})"), self.std_option)
        )
        self.add_to_menu((uw.Divider(), self.std_option))
        self.add_to_menu(
            (
                uw.Button("      Ethernet", on_press=self.on_ethernet_selected),
                self.std_option,
            )
        )
        self.add_to_menu((uw.Divider(), self.std_option))
        self.add_to_menu(
            (uw.Text(f"Wireless networks (HW: {wlan0.hwaddr})"), self.std_option)
        )

        self.update()

        for net in self.networks.values():
            self.add_to_menu(
                (
                    uw.Button(
                        label=text_for(net),
                        on_press=functools.partial(self.on_wifi_selected, net.ident),
                    ),
                    self.std_option,
                )
            )
        self.update()

    def on_error(self, message: str = ""):
        self.menu.contents.clear()
        self.add_to_menu(
            (uw.Text(f"❌ {message}", align=uw.Align.CENTER), self.std_option),
        )
        self.add_to_menu(
            (
                uw.Button("OK", lambda _: self.reset()),
                self.std_option,
            )
        )
        self.menu.focus_position = len(self.menu.contents) - 1
        self.update()

    def on_success(self, message: str = ""):
        self.statuses = self.get_statuses()
        self.menu.contents.clear()
        self.add_to_menu(
            (uw.Text(f"✅ {message}", align=uw.Align.CENTER), self.std_option)
        )
        self.add_to_menu(
            (
                uw.Button("OK", lambda _: self.app.switch_to("loading")),
                self.std_option,
            )
        )
        self.menu.focus_position = len(self.menu.contents) - 1
        self.update()

    def on_ethernet_selected(self, *args):  # noqa: ARG002
        self.remove_statuses()
        self.menu.contents.clear()
        spinner = SpinnerText("Configuring network for Ethernet…")
        self.add_to_menu((spinner, self.std_option))
        spinner.animate(self.uloop)
        self.update()

        res = apply_dhcp(iface=ETH_IFACE)
        if not res.success:
            return self.on_error("Failed to connect Ethernet. Reboot and retry.")
        try:
            nmdevice.connect(ifname=ETH_IFACE)
        except Exception:
            return self.on_error("Failed to connect Ethernet. Reboot and retry.")

        # disconnect WiFi
        if (
            self.host.network.ifaces[WL_IFACE].connected
            and self.host.network.ifaces[WL_IFACE].connection
        ):
            try:
                nmconn.delete(name=self.host.network.ifaces[WL_IFACE].connection)
            except Exception:
                ...

        self.on_success("Ethernet now configured (DHCP)")

    def on_wifi_selected(self, ident: str, *args):  # noqa: ARG002
        self.remove_statuses()
        self.menu.contents.clear()
        self.network = self.networks[ident]

        if not self.network.dev.security:
            return self.on_passphrase_set(None, None)

        self.passphrase_field = DoneEdit(
            f"Type in passphrase for Network {self.network.name} "
            f"{self.network.security} ({self.network.freq}) ",
            "",
        )
        uw.connect_signal(self.passphrase_field, "done", self.on_passphrase_set)

        self.add_to_menu(
            (self.passphrase_field, self.std_option),
        )
        self.update()

    def on_passphrase_set(
        self, _edit: uw.Edit | None, new_edit_text: str | None
    ) -> None:
        self.menu.contents.clear()
        self.loading_text.set_message(
            f"Connecting to {self.network.name} using “{new_edit_text}”…"
            if new_edit_text is not None
            else f"Connecting to {self.network.name}…"
        )
        self.add_to_menu((self.loading_text, self.std_option))
        self.loading_text.animate(self.uloop)
        self.update()
        Thread(
            target=self.connect_to_wifi, kwargs={"password": new_edit_text or ""}
        ).start()

    def connect_to_wifi(self, password: str):
        try:
            nmdevice.wifi_connect(ssid=self.network.bssid, password=password)
        except Exception:
            self.loading_text.done("")
            return self.on_error(
                f"Failed to connect to {self.network.name}. "
                "Was the passphrase correct?"
            )
        else:
            time.sleep(2)

        res = apply_dhcp(iface=WL_IFACE)
        if not res.success:
            self.loading_text.done("")
            return self.on_error(
                f"Failed to get an IP address from {self.network.name}"
            )

        # disconnect Ethernet
        try:
            nmconn.delete(name=self.host.network.ifaces[ETH_IFACE].connection)
        except Exception:
            raise

        self.loading_text.done("")
        return self.on_success(f"WiFi now configured: {self.network.name}")

    def on_cancel(self, *args):  # noqa: ARG002
        self.app.switch_to("loading")
