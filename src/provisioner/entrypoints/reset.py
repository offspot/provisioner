import shutil
import subprocess
import sys

import orjson

mount_bin: str = shutil.which("mount") or ""
umount_bin: str = shutil.which("umount") or ""
losetup_bin: str = shutil.which("losetup") or ""
if not all((mount_bin, umount_bin, losetup_bin)):
    raise SystemError("Missing binary")


def get_mounts() -> list[str]:
    mount = subprocess.run([mount_bin], check=True, text=True, capture_output=True)
    return [
        line.split()[0]
        for line in mount.stdout.splitlines()
        if line.split()[0].startswith("/dev/loop")
    ]


def unmount(mounts: list[str]) -> bool:
    success = True
    for mount in mounts:
        print(f"Unmounting {mount}…")
        umount = subprocess.run([umount_bin, mount], check=False)
        success &= umount.returncode != 0
    return success


def autodetach():
    print("Auto detaching all loops…")
    subprocess.run([losetup_bin, "-D"], check=True, text=True)


def get_loops() -> list[str]:
    # first try to auto detach all
    losetup = subprocess.run(
        [losetup_bin, "--json"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [dev["name"] for dev in orjson.loads(losetup.stdout.strip())["loopdevices"]]


def detach(loops: list[str]) -> bool:
    success = True
    for loop in loops:
        print(f"Detaching {loop}…")
        losetup = subprocess.run([losetup_bin, "-d", loop], check=False)
        success &= losetup.returncode != 0
    return success


def main() -> int:
    # check mounted loops
    mounts = get_mounts()
    print(f"Found {len(mounts)} mounts: {', '.join(mounts)}")
    loops = get_loops()
    print(f"Found {len(loops)} loops: {', '.join(loops)}")

    succeeded = unmount(mounts)

    autodetach()
    succeeded &= detach(get_loops())

    if not succeeded:
        print("Could not reset properly…")
        print(f"- mounts: {', '.join(get_mounts())}")
        print(f"- loops: {', '.join(get_loops())}")
        return 1

    print("All good!")
    return 0


def entrypoint():
    sys.exit(main())
