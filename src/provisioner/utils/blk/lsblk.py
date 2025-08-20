from __future__ import annotations

import subprocess

# from dataclasses import asdict
from pathlib import Path
from pprint import pp
from typing import NotRequired, TypedDict

import orjson
from attr import asdict

from provisioner.context import Context
from provisioner.utils.blk.devices import Device, DeviceType, Disk, Partition

context = Context.get()
logger = context.logger


LsblkChildEntry = TypedDict(
    "LsblkChildEntry",
    {
        "name": str,
        "maj:min": str,
        "rm": bool,
        "size": int,
        "ro": bool,
        "type": str,
        # "mountpoint": str,
        "mountpoints": list[str | None],
        "model": str | None,
        "fstype": str | None,
        "fssize": int,
        "hotplug": bool,
        "label": str,
        "parttypename": str,
        "partlabel": str,
        "partuuid": str,
        "path": str,
        "pttype": "str",
        "tran": "str",
        "uuid": str,
        "vendor": str,
        "phy-sec": int,
        "state": str,
    },
)


class LsblkEntry(LsblkChildEntry):
    children: NotRequired[list[LsblkChildEntry]]


class LsblkOutput(TypedDict):
    blockdevices: list[LsblkEntry]


def parse_lsblk(
    payload: LsblkEntry | LsblkChildEntry,
    parent: Device | None = None,
) -> Device:
    major, minor = [int(part) for part in str(payload["maj:min"]).split(":", 1)]
    dev_type = DeviceType[str(payload["type"])]
    mountpoints = [Path(str(path)) for path in payload["mountpoints"] if path]

    npayload = dict(**payload)
    try:
        del npayload["mountpoint"]
    except KeyError:
        ...
    npayload["major"] = major
    npayload["minor"] = minor
    npayload["type"] = dev_type
    npayload["mountpoints"] = mountpoints
    npayload["path"] = Path(payload["path"])
    npayload["sector_size"] = payload["phy-sec"]
    npayload["vendor"] = (payload.get("vendor") or "").strip()
    npayload["model"] = (payload.get("model") or "").strip()
    npayload["parent"] = parent
    return Device(**npayload)


def get_devices_from_lsblk_payload(
    payload: LsblkOutput,
) -> list[Device]:
    devices: list[Device] = []

    for device_repr in payload.get("blockdevices", []):
        device = parse_lsblk(device_repr)

        devices.append(device)
        children = device_repr.get("children", [])
        if children:
            for child_repr in children:
                child = parse_lsblk(child_repr, parent=device)
                devices.append(child)
    return devices


def get_devices_from_lsblk_json(text: str) -> list[Device]:
    payload: LsblkOutput = orjson.loads(text)
    return get_devices_from_lsblk_payload(payload)


def get_devices() -> list[Device]:
    ps = subprocess.run(
        ["/usr/bin/lsblk", "--json", "--bytes", "--output-all"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if ps.returncode:
        logger.error(f"lsblk returned {ps.returncode}")
        logger.debug(ps.stdout)
        return []
    try:
        # pp(ps.stdout.strip())
        return get_devices_from_lsblk_json(ps.stdout.strip())
    except Exception as exc:
        logger.error(f"Failed to parse lsblk's output: {exc}")
        logger.exception(exc)
        return []


def get_disks_from_devices(devices: list[Device]) -> dict[str, Disk]:
    disks: dict[str, Disk] = {}

    for device in devices:
        if not device.size:
            logger.debug(f"Excluding device {device.name} as is zero size")
            continue
        if device.type == DeviceType.disk:

            # pdb.set_trace()
            disks[device.name] = Disk(**asdict(device))
            continue
        elif device.type == DeviceType.part:
            if not device.parent:
                raise OSError("Partition wihtout parent")
            if device.parent.name not in disks:
                logger.warning(
                    f"Device {device.name}: parent ({device.parent}) not in list"
                )
                continue
            part = Partition(**asdict(device), disk=disks[device.parent.name])
            disks[device.parent.name].add_part(partition=part)
    return disks


if __name__ == "__main__":

    text = """{
   "blockdevices": [
      {
         "name": "nvme0n1",
         "maj:min": "259:0",
         "rm": false,
         "size": 256060514304,
         "ro": false,
         "type": "disk",
         "mountpoints": [
             null
         ],
         "children": [
            {
               "name": "nvme0n1p1",
               "maj:min": "259:1",
               "rm": false,
               "size": 536870912,
               "ro": false,
               "type": "part",
               "mountpoints": [
                   "/boot/firmware"
               ]
            },{
               "name": "nvme0n1p2",
               "maj:min": "259:2",
               "rm": false,
               "size": 255515254784,
               "ro": false,
               "type": "part",
               "mountpoints": [
                   "/"
               ]
            }
         ]
      }
   ]
}
"""
    from pprint import pp

    pp(get_devices_from_lsblk_json(text))
