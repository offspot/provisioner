from provisioner.context import Context
from provisioner.utils.blk.manager import BlockDevicesManager
from provisioner.utils.clock import ClockManager
from provisioner.utils.network import NetworkManager
from provisioner.utils.raspberry import (
    BootOrder,
    get_bootorder,
    get_model,
    get_serial_number,
)

context = Context.get()
logger = context.logger


class ProvisionHost:
    model: str
    serial_number: str
    boot_order: BootOrder | None
    dev: BlockDevicesManager
    network: NetworkManager
    clock: ClockManager

    def __init__(self) -> None: ...

    def query_all(self) -> None:
        self.query_ids()
        self.query_devices()
        self.query_hwclock()
        self.query_network()

    def query_ids(self) -> None:
        self.model = get_model()
        self.serial_number = get_serial_number()
        try:
            self.boot_order = get_bootorder()
        except Exception as exc:
            logger.debug("Failed to read boot_order: {exc}")
            logger.exception(exc)
            self.boot_order = None

    def query_devices(self) -> None:
        self.dev = BlockDevicesManager()
        self.dev.query()

    def query_network(self) -> None:
        self.network = NetworkManager()
        self.network.query()

    def query_hwclock(self) -> None:
        self.clock = ClockManager()
        self.clock.query()

    @property
    def auto_provision_ready(self) -> bool:
        # TODO
        return self.clock.tdctl.all_good and bool(self.dev.target_disk)
