import shutil
from pathlib import Path

from provisioner.context import Context
from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount, mount_to_temp
from provisioner.utils.misc import run_step_command

DOCKER_LOAD_BASH_SCRIPT = r"""
!#/bin/bash

set -e

echo "mounting cgroupfs"
cgroupfs-mount

echo "starting balena engine"
/usr/local/bin/balena-engine-daemon &
sleep 10

echo "starting images loader"
/usr/sbin/docker-images-loader.py

echo "listing loaded images"
docker images

echo "unmounting cgroupfs"
cgroupfs-umount

echo "done."
"""

context = Context.get()
logger = context.logger
mount_bin = shutil.which("mount")
umount_bin = shutil.which("umount")


class DockerStep(Step):

    ident: str = "docker"
    name: str = "Load OCI images onto Docker"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:
        root_dev = self.environment.target_disk.path  # /dev/nvme0n1
        root_part_dev = root_dev.with_name(f"{root_dev.name}p2")  # /dev/nvme0n1p2
        data_part_dev = root_dev.with_name(f"{root_dev.name}p3")  # /dev/nvme0n1p2
        debug_text = f"{root_dev=}\n{root_part_dev=}\n{data_part_dev=}\n"

        # mount root partition as basis for chroot
        try:
            self.mountpoint = mount_to_temp(root_part_dev, rw=True)
            mountpoint = self.mountpoint
        except Exception:
            return StepResult(
                succeeded=False,
                error_text="Failed to mount root partition",
                debug_text=debug_text,
            )
        else:
            debug_text += f"{mountpoint=}\n"

        # mount data partition under its data/
        try:
            mount(data_part_dev, mountpoint.joinpath("data"), rw=True)
        except Exception:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to mount data partition",
                debug_text=debug_text,
            )

        # copy cgroupsfs scripts to chroot for in-chroot use
        try:
            if not mountpoint.joinpath("usr/bin/cgroupfs-mount").exists():
                for name in ("mount", "umount"):
                    shutil.copy2(
                        Path(f"/usr/bin/cgroupfs-{name}"),
                        mountpoint.joinpath(f"usr/bin/cgroupfs-{name}"),
                    )
        except Exception:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to copy cgroupfs-mount scripts",
                debug_text=debug_text,
            )

        # mount proc, sys and dev
        ps = run_step_command(
            [mount_bin, "-t", "proc", "/proc", str(mountpoint.joinpath("proc"))],
            verbose=verbose,
        )
        if ps.returncode != 0:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to mount proc into chroot",
                debug_text=debug_text,
            )
        ps = run_step_command(
            [mount_bin, "-t", "sysfs", "/sys", str(mountpoint.joinpath("sys"))],
            verbose=verbose,
        )
        if ps.returncode != 0:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to mount sysfs into chroot",
                debug_text=debug_text,
            )

        ps = run_step_command(
            [mount_bin, "--rbind", "/dev", str(mountpoint.joinpath("dev"))],
            verbose=verbose,
        )
        if ps.returncode != 0:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to rbind-mount /dev into chroot",
                debug_text=debug_text,
            )

        # copy resolv.conf so chroot can use DNS
        try:
            shutil.copy2(
                Path("/etc/resolv.conf"),
                mountpoint.joinpath("etc/resolv.conf"),
            )
        except Exception:
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to copy resolv.conf",
                debug_text=debug_text,
            )

        # write shell script to target fs
        try:
            script_fpath = mountpoint.joinpath(
                "usr/local/bin/load-images-from-chroot.sh"
            )
            script_fpath.write_text(DOCKER_LOAD_BASH_SCRIPT)
            script_fpath.chmod(0x655)
        except Exception as exc:
            self.unmount_everything(verbose=verbose)
            logger.exception(exc)
            return StepResult(
                succeeded=False,
                error_text="Failed to copy images loader script",
                debug_text=debug_text,
            )
        if verbose:
            logger.info(f"{script_fpath=}:\n{script_fpath.read_text()}")

        script_path = str(Path("/") / script_fpath.relative_to(mountpoint))
        if verbose:
            command = [script_path]
        else:
            command = ["/bin/bash", "-c", f"{script_path} >/dev/null 2>/dev/null"]
        ps = run_step_command(
            [shutil.which("chroot"), str(mountpoint), *command],
            verbose=verbose,
            dont_capture=not verbose,
        )
        if ps.returncode != 0:
            # cgroupfs-umount is part of the script
            # and most likely didn't run if script failed
            run_step_command(
                [shutil.which("chroot"), str(mountpoint), "cgroupfs-umount"],
                verbose=verbose,
            )
            self.unmount_everything(verbose=verbose)
            return StepResult(
                succeeded=False,
                error_text="Failed to run chroot loader script",
                debug_text=debug_text,
            )

        self.unmount_everything(verbose=verbose)

        return StepResult(succeeded=True)

    def unmount_everything(self, *, verbose: bool = False):
        if not getattr(self, "mountpoint", False):
            return
        mountpoint = self.mountpoint

        # unmount everything
        for mnt in ("data", "dev", "proc", "sys"):
            run_step_command(
                [
                    umount_bin,
                    "--recursive",
                    str(self.mountpoint.joinpath(mnt)),
                ],
                verbose=verbose,
            )
            run_step_command(
                [
                    umount_bin,
                    "-l",
                    "--recursive",
                    str(self.mountpoint.joinpath(mnt)),
                ],
                verbose=verbose,
            )
        run_step_command([umount_bin, "--recursive", str(mountpoint)])
        run_step_command([umount_bin, "-l", "--recursive", str(mountpoint)])

        # remount /dev/pts which gets unmounted from its host location
        # and breaks ptys
        run_step_command(
            [mount_bin, "none", "-t", "devpts", "/dev/pts"], verbose=verbose
        )

    def cleanup(self, *, verbose: bool = False) -> StepResult:
        self.unmount_everything(verbose=verbose)
        return StepResult(succeeded=True)
