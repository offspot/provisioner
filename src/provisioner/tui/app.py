import asyncio
import os
import signal
import sys
import threading
import traceback
from traceback import print_exception
from types import FrameType

import urwid as uw

from provisioner.constants import RC_EXIT
from provisioner.context import Context
from provisioner.host import ProvisionHost

uw.set_encoding("UTF-8")
aio_loop = asyncio.get_event_loop()
context = Context.get()
logger = context.logger


def threading_excepthook(args, /):
    """Handle uncaught Thread.run() exception."""

    if sys is not None and sys.stderr is not None:
        stderr = sys.stderr
    elif args.thread is not None:
        stderr = args.thread._stderr
        if stderr is None:
            # do nothing if sys.stderr is None and sys.stderr was None
            # when the thread was created
            return
    else:
        # do nothing if sys.stderr is None and args.thread is None
        return

    if args.thread is not None:
        name = args.thread.name
    else:
        name = threading.get_ident()
    print(f"Exception in thread {name}:", file=stderr, flush=True)
    print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=stderr)
    stderr.flush()


threading.excepthook = threading_excepthook

def _exception_handler(loop, context):  # noqa: ARG001
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
        # TODO: handle exception in UI
        logger.exception(message)
    except Exception as exc:
        ...
        logger.exception("Unable to show exception: " + str(exc))


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
        ("streak", "", "", "", "#fff,bold", "#f70"),
        ("inside", "", "", "", "", "#EB2"),
        ("outside", "", "", "", "", "#FD5"),
        ("bg", "", "", "", "", "#f70"),
        ("bg_prov", "", "", "", "#fff", "#000"),
        ("highlight_prov", "", "", "", "#fff,bold", "#000"),
        ("disabled_prov", "", "", "", "#cfcfcf", "#000"),
        ("logo", "", "", "", "#fff", "#f70"),
        ("btn_lines", "", "", "", "#000", "#f70"),
        ("btn_lines_focus", "", "", "", "#fff", "#f70"),
        ("btn", "", "", "", "#fff", "#000"),
        ("btn_focus", "", "", "", "#000", "#fff"),
        ("confirm_btn", "", "", "", "#fff", "#000"),
        ("confirm_btn_focus", "", "", "", "#000", "#fff"),
        ("popup", "", "", "", "#fff", "#1bf"),
        ("popup_question", "", "", "", "#fff", "#1bf"),
        ("popup_cancel_btn", "", "", "", "#000", "#1bf"),
        ("popup_cancel_btn_focus", "", "", "", "#fff", "#1bf"),
        ("popup_cancel_btn_lines", "", "", "", "#000", "#1bf"),
        ("popup_cancel_btn_lines_focus", "", "", "", "#fff", "#1bf"),
        ("popup_confirm_btn", "", "", "", "#000", "#1bf"),
        ("popup_confirm_btn_focus", "", "", "", "#fff", "#1bf"),
        ("popup_confirm_btn_lines", "", "", "", "#000", "#1bf"),
        ("popup_confirm_btn_lines_focus", "", "", "", "#fff", "#1bf"),
        ("excelent-signal", "", "", "", "#008300", "#f70"),
        ("great-signal", "", "", "", "#008300", "#f70"),
        ("correct-signal", "", "", "", "#ffff00", "#f70"),
        ("poor-signal", "", "", "", "#ff0000", "#f70"),
        ("bad-signal", "", "", "", "#ff0000", "#f70"),
        ("success-status", "", "", "", "#008300,bold", "#f70"),
        ("error-status", "", "", "", "#f00", "#f70"),
        ("pg normal", "", "", "", "#fff", "#000"),
        ("pg complete", "", "", "", "#fff", "#ff00ff"),
        ("pg smooth", "", "", "", "#ff00ff", "#000"),
        ("prov success", "", "", "", "#fff", "#008300"),
        ("prov error", "", "", "", "#fff", "#f00"),
        ("prov spinner", "", "", "", "#ff00ff", "#000"),
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
        self.uloop.screen.set_terminal_properties(  # pyright: ignore reportAttributeAccessIssue
            colors=2**24
        )

        # pipe to request UI update (will happen on main thread)
        self.update_pipe = self.uloop.watch_pipe(lambda _: None)

        from provisioner.tui.pane import Pane  # noqa: PLC0415

        self.pane: Pane | None = None

    def on_unhandled_input(self, key: str | tuple[str, int, int, int]) -> None:
        if key == "f5":
            if self.pane:
                self.pane.refresh()
        if key in {"q", "Q"}:
            self.stop(exit_code=RC_EXIT)
        # print(f"Received {key=}", flush=True)

    def reset_ui(self):
        self.uloop.widget = uw.AttrMap(self.placeholder, "bg")
        if self.pane:
            self.pane.destroy()
            self.pane = None

    def switch_to(self, pane: str):
        self.reset_ui()
        self.update()
        from provisioner.tui.loading import LoadingPane  # noqa: PLC0415
        from provisioner.tui.network import NetworkPane  # noqa: PLC0415
        from provisioner.tui.pane import ExitPane  # noqa: PLC0415
        from provisioner.tui.provision import ProvisionPane  # noqa: PLC0415

        self.pane = {
            "loading": LoadingPane,
            "exit": ExitPane,
            "network": NetworkPane,
            "provision": ProvisionPane,
        }[pane](self)

    def update(self):
        """request UI to update"""
        try:
            os.write(self.update_pipe, b" ")
        except OSError:
            pass

    def start(self, pane: str = "loading"):
        self.switch_to(pane=pane)

        self.uloop.start()
        aio_loop.run_forever()
        aio_loop.stop()

    def stop(self, exit_code: int):
        self.exit_code = exit_code
        # self.on_unhandled_input(key="q")
        if self.pane:
            try:
                self.pane.stop()
            except Exception:
                ...
        if self.uloop:
            try:
                aio_loop.stop()
            except Exception:
                ...
            try:
                self.uloop.stop()
            except Exception:
                ...
        try:
            os.close(self.update_pipe)
        except Exception:
            ...
        sys.exit(self.exit_code)


def main() -> int:
    app = App()

    def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
        print("\n", flush=True)  # noqa: T201
        logger.info(f"Received {signal.Signals(signum).name}/{signum}. Exiting")
        app.stop(exit_code=128 + signum)
        sys.exit(app.exit_code)  # shouldn't be necessary

    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGQUIT, exit_gracefully)

    app.start(pane="loading")

    return app.exit_code
