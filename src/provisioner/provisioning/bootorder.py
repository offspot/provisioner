from provisioner.context import Context
from provisioner.provisioning.common import Step, StepResult
from provisioner.utils.raspberry import update_eeprom

context = Context.get()
logger = context.logger


class BootOrderStep(Step):

    ident: str = "boot"
    name: str = "Change BOOT_ORDER and HDMI_DELAY"
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def run(self, *, verbose: bool = False) -> StepResult:
        try:
            update_eeprom(verbose=verbose)
        except Exception as exc:
            logger.error(f"Failed to update EEPROM: {exc}")
            logger.exception(exc)
            return StepResult(
                succeeded=False,
                error_text="Failed to update EEPROM",
                debug_text=str(exc),
            )

        return StepResult(succeeded=True)
