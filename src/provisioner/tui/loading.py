import time
from threading import Thread

import urwid as uw

from provisioner.constants import (
    ASCII_LOGO,
    RC_ADVANCED,
    RC_HALT,
    RC_REBOOT,
    REFRESHING_INTERVAL_SECONDS,
)
from provisioner.tui.boxbutton import BoxButton, ConfirmingBoxButton, InfoPopupBoxButton
from provisioner.tui.pane import Pane
from provisioner.tui.spinner import SpinnerText


class LoadingPane(Pane):
    def render(self):
        self.keep_refreshing = False

        self.loading_text = SpinnerText("Gathering information…", align="center")

        # paint solid background with vertical stack
        self.main_widget = uw.Filler(uw.Pile([], focus_item=1), valign="top")
        pile = self.pile

        # paint logo with padding
        self.append_to(pile, self.a_divider)
        for line in ASCII_LOGO.splitlines():
            self.append_to(pile, uw.Text(("logo", line), align="center"))
        self.append_to(pile, uw.Divider(top=4))

        # paint a text line surrounded by two lines of decor
        div = self.a_divider
        outside = uw.AttrMap(div, "outside")
        inside = uw.AttrMap(div, "inside")
        streak = uw.AttrMap(self.loading_text, "streak")
        for item in [outside, inside, streak, inside, outside]:
            self.append_to(pile, item)

        self.menu = uw.Columns(
            [
                (
                    "weight",
                    25,
                    ConfirmingBoxButton(
                        "Restart",
                        on_press=self.on_restart_selected,
                        question="Do you want to reboot now?\n"
                        "Remove ProvisionOS media if you're done provisioning.",
                    ),
                ),
                (
                    "weight",
                    25,
                    ConfirmingBoxButton(
                        "Shutdown",
                        on_press=self.on_shutdown_selected,
                        question="Do you want to shut the device down now?",
                    ),
                ),
                ("weight", 25, BoxButton("Advanced mode", self.on_advanced_selected)),
            ]
        )
        self.append_to(pile, self.menu)
        pile.focus_item = self.menu

        self.status = "init"

        self.refresh()

    def refresh(self, *args):  # noqa: ARG002
        if self.status == "gathering":
            return
        # remove menu if present
        if self.status == "ready":
            self.menu.contents.pop(0)
            self.menu.contents.pop(0)

        self.show_as_loading()

        # start thread gathering infos from host
        Thread(target=self.gather_infos, daemon=True).start()

    def show_as_loading(self):
        """display the spinner"""
        self.status = "gathering"
        self.loading_text.set_message("Gathering information…")
        # request spinner text to animate
        self.loading_text.animate(self.uloop)
        self.update()

    def show_as_ready(self, *, pop_menu: bool):
        """show the manu according to status"""
        if pop_menu:
            self.menu.contents.pop(0)
            self.menu.contents.pop(0)

        self.loading_text.done(
            f"Ready for {self.host.model!s} – "  # noqa: RUF001
            f"S/N: {self.host.serial_number.upper()}"
        )
        self.update()
        net_warning = "" if self.host.network.all_good else "⚠️  "
        self.menu.contents.insert(
            0,
            (
                BoxButton(f"{net_warning}Network", self.on_network_selected),
                (uw.WHSettings.WEIGHT, 25, True),
            ),
        )
        ready, message = self.host.provision_ready
        self.menu.contents.insert(
            0,
            (
                (
                    BoxButton("Provision", self.on_provision_selected)
                    if ready
                    else InfoPopupBoxButton(
                        label="🚫  Provision",
                        message=f"Unable to provision:\n{message}",
                    )
                ),
                (uw.WHSettings.WEIGHT, 25, True),
            ),
        )
        self.menu.focus_col = 0
        self.update()
        self.status = "ready"

    def gather_infos(self):
        self.host.query_all()
        self.show_as_ready(pop_menu=False)

        self.keep_refreshing = True
        Thread(target=self.keep_refreshing_network, daemon=True).start()

    def do_refresh_network(self):
        self.host.query_network()
        self.host.query_hwclock()

    def keep_refreshing_network(self):
        sleep_interval = 0.2
        ticks = REFRESHING_INTERVAL_SECONDS / sleep_interval
        counter = 0
        while self.keep_refreshing:
            if self.status != "ready":
                time.sleep(1)
                continue
            if counter >= ticks:
                counter = 0
                self.show_as_loading()
                self.do_refresh_network()
                self.show_as_ready(pop_menu=True)
            else:
                time.sleep(sleep_interval)
                counter += 1

    def stop(self):
        self.keep_refreshing = False

    def on_provision_selected(self, *args):  # noqa: ARG002
        self.app.switch_to("provision")

    def on_network_selected(self, *args):  # noqa: ARG002
        self.app.switch_to("network")

    def on_restart_selected(self, *args):  # noqa: ARG002
        self.app.stop(exit_code=RC_REBOOT)

    def on_shutdown_selected(self, *args):  # noqa: ARG002
        self.app.stop(exit_code=RC_HALT)

    def on_advanced_selected(self, *args):  # noqa: ARG002
        self.app.stop(exit_code=RC_ADVANCED)
