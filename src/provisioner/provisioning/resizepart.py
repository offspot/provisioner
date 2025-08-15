import os
import re
import shutil
from pathlib import Path

from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.misc import run_step_command


class ResizePartitionStep(Step):

    ident: str = "resize-data"
    name: str = "Resize Hotspot's third partition"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:

        root_dev = self.environment.target_disk.path  # /dev/nvme0n1
        boot_part_dev = root_dev.with_name(f"{root_dev.name}p1")  # /dev/nvme0n1p1
        root_part_dev = root_dev.with_name(f"{root_dev.name}p2")  # /dev/nvme0n1p2
        data_part_dev = root_dev.with_name(f"{root_dev.name}p3")  # /dev/nvme0n1p3
        data_part_num = int(
            Path(
                f"/sys/block/{root_dev.name}/{data_part_dev.name}/partition"
            ).read_text()
        )  # 3
        debug_text = (
            f"{root_dev=}, {boot_part_dev=}, "
            f"{root_part_dev=}, {data_part_dev=}, {data_part_num=}"
        )

        # read partition table to extract sectors
        ps = run_step_command(
            [shutil.which("parted"), "-m", str(root_dev), "unit", "s", "print"],
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to resize partition",
                debug_text=debug_text,
            )
        partition_table = ps.stdout.strip()
        # data partition is last (so last line), we get end sector num
        data_part_end = int(
            partition_table.splitlines()[-1].split(":")[2].replace("s", "")
        )

        # target device size in sectors, minus one
        target_end = int(Path(f"/sys/block/{root_dev.name}/size").read_text()) - 1

        debug_text += f"{data_part_end=}, {target_end=}, {data_part_dev=}"

        # extract old disk ID
        ps = run_step_command(
            [shutil.which("fdisk"), "-l", str(root_dev)],
            verbose=verbose,
            capture_output=True,
            text=True,
        )
        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to retrieve old Disk ID",
                debug_text=debug_text,
            )
        disk_id_re = re.compile(r"^Disk identifier: 0x(?P<ident>[a-f0-9]{8})$")
        for line in ps.stdout.strip().splitlines():
            if match := disk_id_re.match(line):
                old_disk_id = match.groupdict()["ident"]

        # generate a new ID for this disk
        new_disk_id = os.urandom(4).hex()

        debug_text += f"{old_disk_id=}, {new_disk_id=}"

        if data_part_end == target_end:
            return StepResult(succeeded=True, success_text="Partition already extended")

        # resize partition (not filesystem)
        ps = run_step_command(
            [
                shutil.which("parted"),
                "-m",
                str(root_dev),
                "u",
                "s",
                "resizepart",
                str(data_part_num),
                str(target_end),
            ],
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to resize partition",
                debug_text=debug_text,
            )

        # check & repair third partition to ensure resize will succeed
        ps = run_step_command(
            [shutil.which("fsck.ext4"), "-y", "-f", "-v", str(data_part_dev)],
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode >= 4:
            return StepResult(
                succeeded=False,
                error_text="Failed to check partition after part resize",
                debug_text=debug_text,
            )

        # resize third partition's filesystem
        ps = run_step_command(
            [shutil.which("resize2fs"), "-f", "-p", str(data_part_dev)],
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to resize filesystem",
                debug_text=debug_text,
            )

        # and recheck to ensure we'll be OK
        ps = run_step_command(
            [shutil.which("fsck.ext4"), "-y", "-f", "-v", str(data_part_dev)],
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode >= 4:
            return StepResult(
                succeeded=False,
                error_text="Failed to check partition after filesystem resize",
                debug_text=debug_text,
            )

        # Update disk identifier
        ps = run_step_command(
            [shutil.which("fdisk"), str(root_dev)],
            input=f"x\ni\n0x{new_disk_id}\nr\nw\n",
            capture_output=True,
            text=True,
            verbose=verbose,
        )
        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to change disk ID",
                debug_text=debug_text,
            )

        # mount root
        mountpoint = mount_to_temp(root_part_dev, rw=True)
        try:
            fstab = mountpoint.joinpath("etc/fstab")
            fstab.write_text(fstab.read_text().replace(old_disk_id, new_disk_id))
            os.sync()
        finally:
            unmount(mountpoint)
            try:
                mountpoint.rmdir()
            except Exception:
                ...

        # mount boot
        mountpoint = mount_to_temp(boot_part_dev, rw=True)
        try:
            cmdline = mountpoint.joinpath("cmdline.txt")
            cmdline.write_text(cmdline.read_text().replace(old_disk_id, new_disk_id))
            os.sync()
        finally:
            unmount(mountpoint)
            try:
                mountpoint.rmdir()
            except Exception:
                ...

        return StepResult(succeeded=True)
