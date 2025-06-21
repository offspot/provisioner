import os
import tempfile
import time
from pathlib import Path
from subprocess import CompletedProcess

from provisioner.context import Context
from provisioner.utils.misc import run_command

context = Context.get()
logger = context.logger


def get_temp_mountpoint(dev_path: Path) -> Path:
    return Path(tempfile.mkdtemp(suffix=".mnt", prefix=f"{dev_path.name}_"))


def mount_to_temp(dev_path: Path) -> Path:
    mountpoint = get_temp_mountpoint(dev_path)
    logger.debug(f"mounting {dev_path} to {mountpoint}")
    ps = run_command(["mount", "-oro", str(dev_path), str(mountpoint)])
    if ps.returncode:
        logger.debug(ps.stdout)
    ps.check_returncode()
    return mountpoint


def unmount(mountpoint: Path) -> CompletedProcess[str]:
    logger.debug(f"unmounting {mountpoint}")
    os.sync()
    ps = run_command(["umount", "-f", str(mountpoint)])
    if ps.returncode:
        logger.debug(ps.stdout)
    ps.check_returncode()
    return ps


def timed_unmount(mountpoint: Path, delay: int | float = 2) -> CompletedProcess[str]:
    logger.debug(f"sleeping {delay}s before unmounting {mountpoint}")
    time.sleep(delay)
    return unmount(mountpoint=mountpoint)
