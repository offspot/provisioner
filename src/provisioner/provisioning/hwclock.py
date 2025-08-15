import shutil

from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.misc import run_step_command


class HardwareClockStep(Step):

    ident: str = "hwclock"
    name: str = "Set Hardware clock to current time"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:
        ci = self.environment.host.clock.tdctl

        if not ci.has_rtc:
            return StepResult(
                succeeded=False, error_text="RTC not found. Probably not a Pi5"
            )

        if not ci.ntp_synced:
            return StepResult(
                succeeded=False,
                error_text="NTP not synced",
                debug_text=f"{ci.utc_time=!s} - {ci.rtc_utc_time=!s}",
                advice="Check Internet connection",
            )
        now = self.environment.host.clock.tdctl.rtc_utc_time
        ps = run_step_command([shutil.which("/sbin/hwclock"), "-w"], verbose=verbose)
        if ps.returncode == 0:
            return StepResult(succeeded=True, debug_text=f"{now!s} UTC")

        return StepResult(succeeded=False, error_text="Failed to write to HW Clock")
