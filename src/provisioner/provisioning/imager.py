import datetime
import errno
import os
import pty
import re
import select
import shutil
import subprocess
import time
from threading import Thread

from provisioner.context import Context
from provisioner.provisioning.common import ImagerStats, Step, StepResult
from provisioner.utils.blk.misc import mount_to_temp, unmount
from provisioner.utils.misc import get_now, run_step_command

context = Context.get()
logger = context.logger


class RpiImager:
    """Subprocess wrapper that reads rpi-imager output to compute stats"""

    stdout: str
    ps: subprocess.Popen[str]

    def __init__(self, args: list[str]) -> None:
        self.args = args

        self.started_on: datetime.datetime = datetime.datetime.now(tz=datetime.UTC)
        self.ended_on: datetime.datetime | None = None

        self.img_hash: str = ""
        self.verify_hash: str = ""

        self.preparing_done: bool = False
        self.write_progress: int = 0
        self.write_done: bool = False
        self.write_duration: float = 0
        self.verify_progress: int = 0
        self.verify_done: bool = False
        self.verify_duration: float = 0
        self.finalizing_done: bool = False

        self.stdout: str = ""

        self.master_stdout, self.slave_stdout = pty.openpty()

        self.output_reader = Thread(target=self.consume_pty)

    def start(
        self,
    ):

        self.ps = subprocess.Popen(
            self.args,
            text=True,
            encoding="UTF-8",
            bufsize=1,
            stdout=self.slave_stdout,
            stderr=subprocess.STDOUT,
            close_fds=True,
            env=os.environ,
        )
        os.close(self.slave_stdout)
        self.output_reader.start()

    def stop(self):
        self.ps.kill()

    def consume_pty(self):
        while self.ps.returncode is None:
            self.read_output()
            self.parse()

    def read_output(self):
        bufsize = 1024
        timeout = 0.5  # seconds
        readable = [self.master_stdout]
        try:
            ready, _, _ = select.select(readable, [], [], timeout)
            if ready:
                for fd in ready:
                    try:
                        data = os.read(fd, bufsize)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise exc
                        # EIO means EOF on some systems
                        readable.remove(fd)
                        break
                    else:
                        if not data:  # EOF
                            break
                        content = (
                            data.replace(b"\r\n", b"\n")
                            .replace(b"\r", b"\n")
                            .decode("UTF-8")
                        )
                        self.stdout += content
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise exc
            # looks like ps has ended. let's let rest of func cleanup
            logger.debug(f"READ attempt on bad descriptor ; maybe ended? -- {exc}")

        if self.completed:
            logger.debug("UPDATE found ps ended")
            if not self.ended_on:
                self.ended_on = datetime.datetime.now(tz=datetime.UTC)
            try:
                os.close(self.master_stdout)
            except Exception as exc:
                logger.debug(f"Failed to release master stdout: {exc}")
            return

    @property
    def suceeded(self) -> bool:
        return self.ps.returncode == 0

    @property
    def completed(self) -> bool:
        return self.ps.poll() is not None

    @property
    def duration(self) -> int:
        if not self.ended_on:
            self.ended_on = datetime.datetime.now(tz=datetime.UTC)
        return int((self.ended_on - self.started_on).total_seconds())

    @property
    def progress(self) -> int:
        return (min(100, self.write_progress) + min(100, self.verify_progress)) // 2

    @property
    def step(self) -> str:
        if not self.preparing_done:
            return "Preparing (device and hashes)"
        if not self.write_done:
            return "Writing to disk"
        if not self.verify_done:
            return "Verifying disk"
        if not self.finalizing_done:
            return "Finalizing"
        return "Completed"

    @property
    def returncode(self) -> int:
        return self.ps.returncode

    def update(self) -> bool:
        """whether it has completed"""

        self.parse()

        if self.completed:
            self.parse()
            if not self.ended_on:
                self.ended_on = datetime.datetime.now(tz=datetime.UTC)
            return True
        return False

    def wait(self, timeout: float | None = None) -> int:
        return self.ps.wait(timeout=timeout)

    def parse(self):
        if self.finalizing_done:  # already fully parsed
            return
        lines = self.stdout.splitlines()

        if not self.preparing_done:
            for line in lines:
                if "Writing:" in line or "Done zeroing out" in line:
                    self.preparing_done = True
                    break

        if not self.img_hash:
            for line in lines:
                if match := re.match(
                    r"^Hash of uncompressed image: \"(?P<hash>[a-z0-9]+)\"$", line
                ):
                    self.img_hash = match.groupdict()["hash"]
                    break

        if not self.write_done:
            for line in lines:
                if line.startswith("  Writing:"):
                    if match := re.match(
                        r"^  Writing: (.+)] (?P<percent>\d+) %$", line
                    ):
                        self.write_progress = int(match.groupdict()["percent"])

                if line.startswith("Write done ") or line.startswith("  Verifying:"):
                    self.write_done = True
                    self.write_progress = 100
                    if match := re.match(
                        r"^Write done in (?P<seconds>\d+) seconds.*", line
                    ):
                        self.write_duration = float(match.groupdict()["seconds"])
                        break

        if not self.verify_done:
            for line in lines:
                if line.startswith("  Verifying:"):
                    if match := re.match(
                        r"^  Verifying: (.+)] (?P<percent>\d+) %$", line
                    ):
                        self.verify_progress = int(match.groupdict()["percent"])

                if (
                    line.startswith("Verify done")
                    or line.startswith("Verify hash:")
                    or line.startswith("Writing first block")
                ):
                    self.verify_done = True
                    self.verify_progress = 100

        if not self.verify_duration:
            for line in lines:
                if line.startswith("Verify done"):
                    if match := re.match(
                        r"^Verify done in (?P<seconds>[\d\.]+) seconds.*", line
                    ):
                        self.verify_duration = float(match.groupdict()["seconds"])
                        break

        if self.verify_done and not self.verify_hash:
            for line in lines:
                if match := re.match(r"^Verify hash: \"(?P<hash>[a-z0-9]+)\"$", line):
                    self.verify_hash = match.groupdict()["hash"]
                    break

        if not self.finalizing_done:
            for line in lines:
                if line.startswith("Write successful"):
                    self.finalizing_done = True
                    break


class PiImagerStep(Step):

    ident: str = "imager"
    name: str = "Flash image onto target disk"
    reports_progress: bool = True
    progress_interval_ms: int = 100

    @property
    def progress(self) -> int:
        try:
            return self.imager.progress
        except Exception:
            return 0

    @property
    def progress_text(self) -> str:
        return self.imager.step

    def run(self, *, verbose: bool = False) -> StepResult:

        mountpoint = mount_to_temp(self.environment.image_device.path)
        fpath = mountpoint.joinpath(self.environment.image.relpath)
        target = self.environment.target_disk.path

        stats = ImagerStats(started_on=get_now(), ended_on=get_now())
        if verbose:
            ps = run_step_command(
                [
                    shutil.which("rpi-imager"),
                    "--cli",
                    "--disable-eject",
                    "--debug",
                    str(fpath),
                    str(self.environment.target_disk.path),
                ],
                verbose=True,
            )
        else:
            self.imager = RpiImager(
                args=[
                    shutil.which("rpi-imager") or "/bin/false",
                    "--cli",
                    "--disable-eject",
                    "--debug",
                    str(fpath),
                    str(self.environment.target_disk.path),
                ]
            )
            ps = self.imager
            self.imager.start()

            while not self.imager.update() and not self.imager.completed:
                ...
            time.sleep(1)
            self.imager.parse()

            stats = ImagerStats(
                started_on=self.imager.started_on,
                ended_on=self.imager.ended_on or get_now(),
                preparing_done=self.imager.preparing_done,
                write_progress=self.imager.write_progress,
                write_done=self.imager.write_done,
                write_duration=self.imager.write_duration,
                verify_progress=self.imager.verify_progress,
                verify_done=self.imager.verify_done,
                verify_duration=self.imager.verify_duration,
                finalizing_done=self.imager.finalizing_done,
                duration=self.imager.duration,
            )

        unmount(mountpoint)

        if ps.returncode != 0:
            return StepResult(
                succeeded=False,
                error_text="Failed to flash image to disk",
                debug_text=f"{fpath=}, {target=}",
                imager_stats=stats,
            )
        return StepResult(succeeded=True, imager_stats=stats)
