import datetime
from collections.abc import Generator

from provisioner.context import Context
from provisioner.provisioning.bootorder import BootOrderStep
from provisioner.provisioning.common import Environment, ImplementsProgress, Step
from provisioner.provisioning.docker import DockerStep
from provisioner.provisioning.hwclock import HardwareClockStep
from provisioner.provisioning.imager import PiImagerStep
from provisioner.provisioning.offspotyaml import OffspotYAMLStep
from provisioner.provisioning.resizepart import ResizePartitionStep

context = Context.get()
logger = context.logger


class ProvisionManager:
    STEPS: tuple[type[Step], ...] = (
        HardwareClockStep,
        PiImagerStep,
        BootOrderStep,
        ResizePartitionStep,
        OffspotYAMLStep,
        DockerStep,
    )

    def __init__(
        self,
        environment: Environment,
        progressbar: ImplementsProgress | None = None,
    ):
        self.environment = environment
        self.progressbar: ImplementsProgress | None = progressbar

        self.steps: dict[str, Step] = {}
        self.step_index = -1
        self.started_on: datetime.datetime | None = None
        self.ended_on: datetime.datetime | None = None

    def get_step(self, ident: str) -> Step:
        if ident in self.steps:
            return self.steps[ident]
        for step_t in self.STEPS:
            if step_t.ident == ident:
                self.steps[ident] = step_t(
                    environment=self.environment,
                    step_index=self.step_index,
                    total_steps=len(self.STEPS),
                    progressbar=self.progressbar,
                )
                return self.steps[ident]
        raise KeyError(f"No step for {ident}")

    def __iter__(self) -> Generator[Step, None, None]:
        self.step_index = -1
        for index, step_t in enumerate(self.STEPS):
            self.step_index = index
            yield self.get_step(ident=step_t.ident)

    def __enter__(self):
        self.start()
        yield from self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end()

    def start(self):
        if self.started_on is None:
            self.started_on = datetime.datetime.now(tz=datetime.UTC)

    def end(self):
        if self.ended_on is None:
            self.ended_on = datetime.datetime.now(tz=datetime.UTC)

    @property
    def duration(self) -> float:
        if self.started_on is not None and self.ended_on is not None:
            return (self.ended_on - self.started_on).total_seconds()
        return -1

    def cleanup(self) -> int:
        ret = 0
        for step_t in reversed(self.STEPS):
            step = self.steps[step_t.ident]
            try:
                ret += 1 if not step.cleanup() else 0
            except Exception as exc:
                logger.debug(f"Failed to cleanup {step.ident}")
                logger.exception(exc)
                ret += 1
        return ret
