import os

from provisioner.context import Context
from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.yaml import yaml_dump, yaml_load

context = Context.get()
logger = context.logger


class OffspotYAMLStep(Step):
    ident: str = "offspot"
    name: str = "Update offspot.yaml for runtime configuration"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:
        root_dev = self.environment.target_disk.path  # /dev/nvme0n1
        boot_part_dev = root_dev.with_name(f"{root_dev.name}p1")  # /dev/nvme0n1p1
        mountpoint = mount_to_temp(boot_part_dev, rw=True)
        try:
            offspot_yaml = mountpoint.joinpath("offspot.yaml")
            config = yaml_load(offspot_yaml.read_text())

            config["capabilities"] = config.get("capabilities", {})
            config["capabilities"].update({"change_bootorder": True})

            offspot_yaml.write_text(yaml_dump(config))
            os.sync()
            if verbose:
                logger.info(f"{offspot_yaml=}:\n{offspot_yaml.read_text()}")
        except Exception as exc:
            return StepResult(
                succeeded=False,
                error_text="Failed to enable RTC Battery charging",
                debug_text=str(exc),
            )
        finally:
            unmount(mountpoint)
            try:
                mountpoint.rmdir()
            except Exception:
                ...
        return StepResult(succeeded=True)
