import shutil

from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.misc import run_step_command


class PiImagerStep(Step):

    ident: str = "imager"
    name: str = "Flash image onto target disk"

    def run(self, *, verbose: bool = False) -> StepResult:

        mountpoint = mount_to_temp(self.environment.image_device.path)
        fpath = mountpoint.joinpath(self.environment.image.relpath)
        target = self.environment.target_disk.path
        ps = run_step_command(
            [
                shutil.which("rpi-imager"),
                "--cli",
                "--disable-eject",
                "--debug",
                str(fpath),
                str(self.environment.target_disk.path),
            ],
            verbose=verbose,
        )

        unmount(mountpoint)

        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to flash image to disk",
                debug_text=f"{fpath=}, {target=}",
            )
        return StepResult(succeeded=True, success_text="Flashed Stats")
