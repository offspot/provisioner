import datetime
from abc import abstractmethod
from typing import Protocol

from attrs import define

from provisioner.host import ProvisionHost
from provisioner.utils.blk.devices import Device, Disk
from provisioner.utils.imgprobe import ImageFileInfo


@define
class ImagerStats:
    started_on: datetime.datetime
    ended_on: datetime.datetime
    preparing_done: bool = False
    write_progress: int = 0
    write_done: bool = False
    write_duration: float = 0
    verify_progress: int = 0
    verify_done: bool = False
    verify_duration: float = 0
    finalizing_done: bool = False
    duration: int = 0


@define
class StepResult:
    succeeded: bool
    success_text: str = ""
    error_text: str = ""
    debug_text: str = ""
    advice: str = ""
    imager_stats: ImagerStats | None = None


@define
class Environment:
    host: ProvisionHost
    image: ImageFileInfo
    image_device: Device
    target_disk: Disk

    @property
    def image_fits_target(self) -> bool:
        return self.image.size <= self.target_disk.size


class ImplementsProgress(Protocol):
    @abstractmethod
    def set_completion(self, current: int) -> None:
        raise NotImplementedError()


@define
class Step:

    ident: str = ""
    name: str = ""
    reports_progress: bool = False
    progress_interval_ms: int = 1000

    def __init__(
        self,
        *,
        environment: Environment,
        step_index: int,
        total_steps: int,
        progressbar: ImplementsProgress | None = None,
    ):
        self.environment = environment
        self.step_index = step_index
        self.total_steps = total_steps
        self.progressbar = progressbar
        self.running = False

    @property
    def stepnum(self) -> int:
        return self.step_index + 1

    @property
    def prefix(self) -> str:
        return f"[Step {self.stepnum}/{self.total_steps}]"

    def run(self, *, verbose: bool = False) -> StepResult: ...
    def cleanup(self, *, verbose: bool = False) -> StepResult: ...

    @property
    def progress(self) -> int:
        return 0
