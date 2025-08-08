from attrs import define

from provisioner.host import ProvisionHost
from provisioner.utils.blk.devices import Device, Disk
from provisioner.utils.imgprobe import ImageFileInfo


@define
class StepResult:
    succeeded: bool
    success_text: str = ""
    error_text: str = ""
    debug_text: str = ""
    advice: str = ""


@define
class Environment:
    host: ProvisionHost
    image: ImageFileInfo
    image_device: Device
    target_disk: Disk

    @property
    def image_fits_target(self) -> bool:
        return self.image.size <= self.target_disk.size


@define
class Step:

    ident: str = ""
    name: str = ""

    def __init__(
        self,
        *,
        environment: Environment,
        step_index: int,
        total_steps: int,
    ):
        self.environment = environment
        self.step_index = step_index
        self.total_steps = total_steps

    @property
    def stepnum(self) -> int:
        return self.step_index + 1

    @property
    def prefix(self) -> str:
        return f"[Step {self.stepnum}/{self.total_steps}]"

    def run(self, *, verbose: bool = False) -> StepResult: ...
    def cleanup(self, *, verbose: bool = False) -> StepResult: ...

    @property
    def has_no_progress(self) -> bool:
        return hasattr(self, "progress")
