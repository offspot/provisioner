import datetime
from dataclasses import dataclass
from pathlib import Path

# from pyreadpartitions import DiskInfo, MBRInfo, get_disk_partitions_info
from provisioner.context import Context


@dataclass(kw_only=True)
class ImagePartition:
    bps: int  # bytes per sector
    sectors: int
    index: int
    lba: int
    type: str
    type_code: int

    @property
    def size(self) -> int:
        return self.bps * self.sectors


@dataclass(kw_only=True)
class Image:
    fpath: Path
    size: int
    created_on: datetime.datetime
    partitions: list[ImagePartition]
    is_kiwix_hotspot: bool
    variant: str
    version: str

    @property
    def has_parts(self) -> bool:
        return bool(self.partitions)

    @property
    def nb_partitions(self) -> int:
        return len(self.partitions)

    @property
    def fname(self) -> str:
        return self.fpath.name

    @classmethod
    def from_fs(cls, fpath: Path) -> "Image":
        try:
            size = fpath.resolve().stat().st_size
        except Exception as exc:
            logger.error(f"Failed to stats IMG file {fpath.resolve()}: {exc}")
            raise InvalidImageError(fpath.resolve()) from exc

        with open(fpath.resolve(), "rb") as fp:
            pi: DiskInfo = get_disk_partitions_info(fp)
            if pi.mbr:
                boot_record: MBRInfo = pi.mbr
            elif pi.gpt:
                raise NotImplementedError("Only support MBR boot record for now")
            else:
                raise NotImplementedError("Only support MBR boot record for now")
            partitions = [
                Partition(
                    bps=boot_record.lba_size,
                    sectors=part.sectors,
                    index=part.index,
                    lba=part.lba,
                    type=part.type_str,
                    type_code=part.type,
                )
                for part in boot_record.partitions
            ]
            return Image(
                fpath=fpath.resolve(),
                size=size,
                created_on=created_on,
                partitions=partitions,
            )
