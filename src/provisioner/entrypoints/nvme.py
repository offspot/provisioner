import argparse
import subprocess
import sys
from pathlib import Path

from provisioner.__about__ import __version__
from provisioner.constants import NAME_CLI
from provisioner.context import Context

default_nvme_dev: Path = Path("/dev/nvme0n1")
default_mountpoint: Path = Path("/mnt/nvme")
logger = Context.logger


def prepare_context(raw_args: list[str]) -> tuple[str, bool]:
    parser = argparse.ArgumentParser(
        prog=NAME_CLI,
        description="Kiwix Hotspot Harwdware Provisioner",
        epilog="https://github.com/offspot/provisioner",
    )

    parser.add_argument(
        "--static",
        help=f"Use {default_nvme_dev}p{{1,2,3}} instead of querying provision host",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--debug",
        help="Enable verbose output",
        action="store_true",
        default=Context.debug,
    )

    parser.add_argument(
        "--version",
        help="Display version and exit",
        action="version",
        version=__version__,
    )

    parser.add_argument(
        "action",
        help="Whether to mount or unmount",
        choices=("mount", "unmount"),
    )

    args = parser.parse_args(raw_args)
    # ignore unset values in order to not override Context defaults
    args_dict = {key: value for key, value in args._get_kwargs() if value}
    action = args_dict.pop("action")
    static = args_dict.pop("static", False)

    Context.setup(**args_dict)

    return action, static


def mount_static() -> int:
    from provisioner.utils.blk.misc import mount  # noqa: PLC0415

    has_error = False
    for partnum in (1, 2, 3):
        dev = default_nvme_dev.with_name(f"{default_nvme_dev.name}p{partnum}")
        mnt = default_mountpoint.joinpath(f"p{partnum}")
        mnt.mkdir(parents=True, exist_ok=True)
        try:
            mount(
                dev_path=dev,
                mountpoint=mnt,
                rw=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error(f"Unable to mount {dev!s} to {mnt!s}: {exc!s}")
            has_error = True
            continue
        else:
            logger.info(f"Mounted {dev!s} to {mnt!s}")
    return 0 if not has_error else 1


def unmount_static() -> int:
    from provisioner.utils.blk.misc import unmount  # noqa: PLC0415

    has_error = False
    for partnum in (1, 2, 3):
        mnt = default_mountpoint.joinpath(f"p{partnum}")
        try:
            unmount(mountpoint=mnt)
            mnt.rmdir()
        except subprocess.CalledProcessError as exc:
            logger.error(f"Unable to unmount {mnt!s}: {exc!s}")
            has_error = True
            continue
        else:
            logger.info(f"Un-mounted {mnt!s}")
    return 0 if not has_error else 1


def main() -> int:
    global logger  # noqa: PLW0603
    action, use_static = prepare_context(sys.argv[1:])
    context = Context.get()
    logger = context.logger

    if use_static and action == "mount":
        return mount_static()
    elif use_static:
        return unmount_static()

    from provisioner.host import ProvisionHost  # noqa: PLC0415
    from provisioner.utils.blk.misc import mount, unmount  # noqa: PLC0415

    host = ProvisionHost()
    host.query_devices()
    if not host.dev.nvme_target_disk:
        logger.error("No NVMe target found")
        return 1

    has_error = False

    if action == "mount":
        for partition in host.dev.nvme_target_disk.partitions:
            try:
                dev = partition.path
                mnt = default_mountpoint.joinpath(partition.nickname)
                mnt.mkdir(parents=True, exist_ok=True)
                mount(
                    dev_path=partition.path,
                    mountpoint=mnt,
                    rw=True,
                )
            except subprocess.CalledProcessError as exc:
                logger.error(f"Unable to mount {dev!s} to {mnt!s}: {exc!s}")
                has_error = True
                continue
            else:
                logger.info(f"Mounted {dev!s} to {mnt!s}")
    else:
        for partition in host.dev.nvme_target_disk.partitions:
            try:
                mnt = default_mountpoint.joinpath(partition.nickname)
                unmount(mountpoint=mnt)
                mnt.rmdir()
            except subprocess.CalledProcessError as exc:
                logger.error(f"Unable to unmount {mnt!s}: {exc!s}")
                has_error = True
                continue
            else:
                logger.info(f"Un-mounted {mnt!s}")

    return 0 if not has_error else 1


def entrypoint():
    sys.exit(main())
