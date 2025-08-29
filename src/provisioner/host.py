import datetime

from provisioner.context import Context
from provisioner.utils.blk.manager import BlockDevicesManager
from provisioner.utils.clock import ClockManager
from provisioner.utils.misc import get_now
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

    def __init__(self) -> None:
        self.ready = False
        self.queried_on = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)

    def query_all(self) -> None:
        self.query_ids()
        self.query_devices()
        self.query_network()
        self.query_hwclock()
        self.ready = True
        self.queried_on = get_now()

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
        # in case we are not NTP-synced and we are network-connected
        # re-request NTP sync
        if not self.clock.tdctl.ntp_synced and (self.network and self.network.all_good):
            self.clock.requery()

    @property
    def provision_ready(self) -> tuple[bool, str]:
        """whether conditions are met for no-question provisioning"""
        if not self.dev.nvme_target_disks:
            return False, "No target disk present"
        elif len(self.dev.nvme_target_disks) > 1:
            return (
                False,
                "Multiple target disks present:\n"
                f"{','.join([str(d) for d in self.dev.nvme_target_disks])}",
            )

        if not self.dev.has_at_least_one_image:
            if not self.dev.source_disks:
                return False, "No source image disk present"
            return False, "No image found"
        if not self.network.internet.https:
            return False, "No Internet connection"
        if self.network.is_not_connected:
            return False, "Not connected to network"
        if self.network.is_multi_connected:
            return False, "Is connected to multiple networks"
        if not self.clock.tdctl.ntp_synced:
            return False, "Clock not synced (requires Internet)"
        return True, ""
