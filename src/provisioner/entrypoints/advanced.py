import argparse
import signal
import sys
from types import FrameType

from provisioner.__about__ import __version__
from provisioner.constants import NAME_CLI
from provisioner.context import Context

logger = Context.logger


def prepare_context(raw_args: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog=f"{NAME_CLI}-advanced",
        description="Provisioner Advanced UI",
        epilog="https://github.com/offspot/provisioner",
    )

    parser.add_argument(
        "--debug",
        help="Enable verbose output",
        action="store_true",
        default=Context.debug,
    )

    parser.add_argument(
        "--fake-pi",
        help="[dev] look for Pi-specific files in CWD",
        action="store_true",
        dest="fake_pi",
        default=Context.fake_pi,
    )

    parser.add_argument(
        "--version",
        help="Display version and exit",
        action="version",
        version=__version__,
    )

    args = parser.parse_args(raw_args)
    # ignore unset values in order to not override Context defaults
    args_dict = {key: value for key, value in args._get_kwargs() if value}

    Context.setup(**args_dict)


def main() -> int:
    debug = Context.debug
    try:
        prepare_context(sys.argv[1:])
        context = Context.get()
        debug = context.debug

        from provisioner.cli.menu import main as main_prog
        from provisioner.host import ProvisionHost

        def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
            print("\n", flush=True)
            logger.info(f"Received {signal.Signals(signum).name}/{signum}. Exiting")
            sys.exit(4)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGQUIT, exit_gracefully)

        host = ProvisionHost()
        return main_prog(host=host)
    except Exception as exc:
        logger.error(f"General failure: {exc!s}")
        if debug:
            logger.exception(exc)
        return 1


def entrypoint():
    sys.exit(main())
