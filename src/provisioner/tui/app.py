import asyncio
import signal
import sys
import traceback
from types import FrameType

import urwid as uw

from provisioner.context import Context
from provisioner.host import ProvisionHost

uw.set_encoding("UTF-8")
aio_loop = asyncio.get_event_loop()
context = Context.get()
logger = context.logger


def _exception_handler(loop, context):
    try:
        exception = context.get("exception")
        if not exception:
            raise Exception
        message = (
            "Whoops, something went wrong:\n\n"
            + str(exception)
            + "\n"
            + "".join(traceback.format_tb(exception.__traceback__))
        )
        # self.chatbox = LoadingChatBox(message)
    except Exception:
        ...
        # self.chatbox = LoadingChatBox('Unable to show exception: ' + str(exc))


class ExceptionHandlingLoop(uw.AsyncioEventLoop):
    def run(self):
        self._loop.set_exception_handler(self._custom_exception_handler)
        self._loop.run_forever()

    def set_exception_handler(self, handler):
        self._custom_exception_handler = handler


class App:

    palette = (
        # name, foreground, background, mono, foreground_high, background_high
        ("banner", "", "", "", "#ffa", "#FD5"),
        ("streak", "", "", "", "white,bold", "#f70"),
        ("inside", "", "", "", "", "#EB2"),
        ("outside", "", "", "", "", "#FD5"),
        ("bg", "", "", "", "", "#f70"),
        ("logo", "white", "", "", "white", "#f70"),
        ("btn_lines", "", "", "", "#000", "#f70"),
        ("btn_lines_focus", "", "", "", "#fff", "#f70"),
        ("btn", "", "", "", "#fff", "#000"),
        ("btn_focus", "", "", "", "black", "white"),
        ("confirm_btn", "", "", "", "#fff", "#000"),
        ("confirm_btn_focus", "", "", "", "black", "white"),
        # ("confirm_btn", "", "", "", "#fff", "#000"),
        # ("confirm_btn_focus", "", "", "", "#cdf", "#1bf"),
        ("popup", "", "", "", "white", "#1bf"),
        ("popup_question", "", "", "", "white", "#1bf"),
        ("popup_cancel_btn", "", "", "", "black", "#1bf"),
        ("popup_cancel_btn_focus", "", "", "", "white", "#1bf"),
        ("popup_cancel_btn_lines", "", "", "", "black", "#1bf"),
        ("popup_cancel_btn_lines_focus", "", "", "", "white", "#1bf"),
        ("popup_confirm_btn", "", "", "", "black", "#1bf"),
        ("popup_confirm_btn_focus", "", "", "", "white", "#1bf"),
        ("popup_confirm_btn_lines", "", "", "", "black", "#1bf"),
        ("popup_confirm_btn_lines_focus", "", "", "", "white", "#1bf"),
        ("excelent-signal", "", "", "", "#008300", "#f70"),
        ("great-signal", "", "", "", "#008300", "#f70"),
        ("correct-signal", "", "", "", "#ffff00", "#f70"),
        ("poor-signal", "", "", "", "#ff0000", "#f70"),
        ("bad-signal", "", "", "", "#ff0000", "#f70"),
        ("success-status", "", "", "", "#008300,bold", "#f70"),
        ("error-status", "", "", "", "#f00", "#f70"),
    )

    def __init__(self) -> None:
        self.exit_code = 1
        self.host = ProvisionHost()
        self.placeholder = uw.SolidFill()
        self.custom_loop = ExceptionHandlingLoop(loop=aio_loop)
        self.custom_loop.set_exception_handler(_exception_handler)
        self.uloop = uw.MainLoop(
            self.placeholder,
            palette=self.palette,
            event_loop=self.custom_loop,
            unhandled_input=self.on_unhandled_input,
            handle_mouse=False,
            pop_ups=True,
        )
        self.uloop.screen.set_terminal_properties(colors=2**24)
        from provisioner.tui.pane import Pane

        self.pane: Pane = None

    def on_unhandled_input(self, key: str | tuple[str, int, int, int]) -> None:
        if key in {"q", "Q"}:
            if self.uloop:
                aio_loop.stop()
                self.uloop.stop()
        # print(f"Received {key=}", flush=True)

    def reset_ui(self):
        self.uloop.widget = uw.AttrMap(self.placeholder, "bg")
        if self.pane:
            self.pane.destroy()
            self.pane = None

    def switch_to(self, pane: str):
        self.reset_ui()
        self.update()
        from provisioner.tui.loading import LoadingPane
        from provisioner.tui.network import NetworkPane
        from provisioner.tui.pane import ExitPane

        self.pane = {"loading": LoadingPane, "exit": ExitPane, "network": NetworkPane}[
            pane
        ](self)

    def update(self):
        try:
            self.uloop.draw_screen()
        except Exception:
            ...

    def start(self, pane: str = "loading"):
        self.switch_to(pane=pane)

        self.uloop.start()
        aio_loop.run_forever()
        aio_loop.stop()

    def stop(self, exit_code: int):
        self.exit_code = exit_code
        if self.uloop:
            aio_loop.stop()
            self.uloop.stop()


def main() -> int:

    app = App()

    def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
        print("\n", flush=True)
        app.stop(exit_code=128 + signum)
        logger.info(f"Received {signal.Signals(signum).name}/{signum}. Exiting")
        sys.exit(app.exit_code)

    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGQUIT, exit_gracefully)

    app.start(pane="loading")

    return app.exit_code
