import os

from provisioner.constants import RTC_CHARGING_VOLTAGE
from provisioner.context import Context
from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.raspberry import BootConfig

context = Context.get()
logger = context.logger


class EnableChargerStep(Step):

    ident: str = "charger"
    name: str = "Enable RTC Battery Charger"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:
        root_dev = self.environment.target_disk.path  # /dev/nvme0n1
        boot_part_dev = root_dev.with_name(f"{root_dev.name}p1")  # /dev/nvme0n1p1
        mountpoint = mount_to_temp(boot_part_dev, rw=True)
        try:
            config_path = mountpoint.joinpath("config.txt")
            config = BootConfig.parse(config_path.read_text())
            config.add_key(
                key="dtparam=rtc_bbat_vchg",
                value=str(int(RTC_CHARGING_VOLTAGE * 1000000)),
                cfilter="pi5",
            )
            config_path.write_text(config.serialize())
            os.sync()
            if verbose:
                logger.info(f"{config_path=}:\n{config_path.read_text()}")
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
