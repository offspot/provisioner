import os

from provisioner.constants import RTC_CHARGING_VOLTAGE
from provisioner.context import Context
from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.yaml import yaml_dump, yaml_load

context = Context.get()
logger = context.logger

class OffspotYAMLStep(Step):

    ident: str = "offspot"
    name: str = "Update offspot.yaml for runtime configuration"

    def run(self, *, verbose: bool = False) -> StepResult:
        root_dev = self.environment.target_disk.path  # /dev/nvme0n1
        boot_part_dev = root_dev.with_name(f"{root_dev.name}p1")  # /dev/nvme0n1p1
        mountpoint = mount_to_temp(boot_part_dev, rw=True)
        try:
            offspot_yaml = mountpoint.joinpath("offspot.yaml")
            config = yaml_load(offspot_yaml.read_text())

            # update
            # > set RTC charging voltage (to enable it)
            config["rtc"] = {"charger": int(RTC_CHARGING_VOLTAGE * 10000)}
            # country-update not required

            offspot_yaml.write_text(yaml_dump(config))
            os.sync()
            if verbose:
                logger.info(f"{offspot_yaml=}:\n{offspot_yaml.read_text()}")
        finally:
            unmount(mountpoint)
            try:
                mountpoint.rmdir()
            except Exception:
                ...
        return StepResult(succeeded=True)
