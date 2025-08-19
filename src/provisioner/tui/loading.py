from threading import Thread

import urwid as uw

from provisioner.constants import ASCII_LOGO, RC_ADVANCED, RC_HALT, RC_REBOOT
from provisioner.tui.boxbutton import BoxButton, ConfirmingBoxButton, InfoPopupBoxButton
from provisioner.tui.pane import Pane
from provisioner.tui.spinner import SpinnerText


class LoadingPane(Pane):

    def render(self):
        self.loading_text = SpinnerText("Gathering information…", align="center")

        # paint solid background with vertical stack
        # self.uloop.widget.original_widget = uw.Filler(
        self.main_widget = uw.Filler(uw.Pile([], focus_item=1), valign="top")
        pile = self.main_widget.base_widget  # .base_widget skips the decorations

        # paint logo with padding
        pile.contents.append((uw.Divider(top=0, bottom=0), pile.options()))
        for line in ASCII_LOGO.splitlines():
            pile.contents.append(
                (uw.Text(("logo", line), align="center"), pile.options())
            )
        pile.contents.append((uw.Divider(top=4), pile.options()))

        # paint a text line surrounded by two lines of decor
        div = uw.Divider()
        outside = uw.AttrMap(div, "outside")
        inside = uw.AttrMap(div, "inside")
        streak = uw.AttrMap(self.loading_text, "streak")
        for item in [outside, inside, streak, inside, outside]:
            pile.contents.append((item, pile.options()))

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
        pile.contents.append((self.menu, pile.options()))
        pile.focus_item = self.menu

        # request spinner text to animate
        self.loading_text.animate(self.uloop)

        # start thread gathering infos from host
        thread = Thread(target=self.gather_infos)
        thread.start()

    def gather_infos(self):
        self.host.query_all()
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
