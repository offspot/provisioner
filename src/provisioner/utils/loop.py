import json
import subprocess
from pathlib import Path

from provisioner.context import Context
from provisioner.utils.misc import get_environ

context = Context.get()
logger = context.logger

only_on_debug = context.debug


def get_loopdev() -> str:
    """free loop-device path ready to ease"""
    return subprocess.run(
        ["/usr/bin/env", "losetup", "-f"],
        check=True,
        capture_output=True,
        text=True,
        env=get_environ(),
    ).stdout.strip()


def is_loopdev_free(loop_dev: str):
    """whether a loop-device (/dev/loopX) is not already attached"""
    devices = json.loads(
        subprocess.run(
            ["/usr/bin/env", "losetup", "--json"],
            check=True,
            capture_output=True,
            text=True,
            env=get_environ(),
        ).stdout.strip()
    )["loopdevices"]
    return loop_dev not in [device["name"] for device in devices]


def get_loop_name(loop_dev: str) -> str:
    """name of loop from loop_dev (/dev/loopX -> loopX)"""
    return str(Path(loop_dev).relative_to(Path("/dev")))


def create_block_special_device(dev_path: str, major: int, minor: int):
    """create a special block device (for partitions, inside docker)"""
    logger.debug(f"Create mknod for {dev_path} with {major=} {minor=}")
    subprocess.run(
        ["/usr/bin/env", "mknod", dev_path, "b", str(major), str(minor)],
        check=True,
        capture_output=only_on_debug,
        text=True,
        env=get_environ(),
    )


def attach_to_device(img_fpath: Path, loop_dev: str):
    """attach a device image to a loop-device"""
    subprocess.run(
        ["/usr/bin/env", "losetup", "--partscan", loop_dev, str(img_fpath)],
        check=True,
        capture_output=only_on_debug,
        text=True,
        env=get_environ(),
    )

    # create nodes for partitions if not present (typically when run in docker)
    if not Path(f"{loop_dev}p1").exists():
        logger.debug(f"Missing {loop_dev}p1 on fs")
        loop_name = get_loop_name(loop_dev)
        loop_block_dir = Path("/sys/block/") / loop_name

        if not loop_block_dir.exists():
            raise OSError(f"{loop_block_dir} does not exists")
        for part_dev_file in loop_block_dir.rglob(f"{loop_name}p*/dev"):
            part_path = Path(loop_dev).with_name(part_dev_file.parent.name)
            major, minor = part_dev_file.read_text().strip().split(":", 1)
            create_block_special_device(
                dev_path=str(part_path), major=int(major), minor=int(minor)
            )
    else:
        logger.debug(f"Found {loop_dev}p1 on fs")


def detach_device(loop_dev: str, *, failsafe: bool = False) -> bool:
    """whether detaching this loop-device succeeded"""
    ps = subprocess.run(
        ["/usr/bin/env", "losetup", "--detach", loop_dev],
        check=not failsafe,
        capture_output=only_on_debug,
        text=True,
        env=get_environ(),
    )

    # remove special block devices if still present (when in docker)
    loop_path = Path(loop_dev)
    if loop_path.with_name(f"{loop_path.name}p1").exists():
        logger.debug(f"{loop_dev}p1 not removed from fs")
        for part_path in loop_path.parent.glob(f"{loop_path.name}p*"):
            logger.debug(f"Unlinking {part_path}")
            part_path.unlink(missing_ok=True)
    else:
        logger.debug(f"{loop_dev} properly removed from fs")

    return ps.returncode == 0
