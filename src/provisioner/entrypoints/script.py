import shutil
import subprocess
import sys
from pathlib import Path

from provisioner.constants import RC_ADVANCED, RC_HALT, RC_REBOOT, RC_UI


def main() -> int:
    bin_dir = Path(sys.argv[0]).parent
    if not bin_dir.joinpath("provisioner-ui").exists():
        raise SystemExit("Cant find provisioner-ui")
    sysctl = shutil.which("systemctl") or "systemctl"

    command: list[str] = [str(bin_dir.joinpath("provisioner-ui"))]
    while True:
        try:
            ps = subprocess.run(command, check=False)
        except KeyboardInterrupt as exc:
            print(exc)
            return 128
        except Exception as exc:
            print(exc)
            continue
        if ps.returncode == RC_ADVANCED:
            command = [str(bin_dir.joinpath("provisioner-advanced"))]
            continue
        if ps.returncode == RC_REBOOT:
            command = [sysctl, "reboot"]
            continue
        if ps.returncode == RC_HALT:
            command = [sysctl, "halt"]
            continue
        if ps.returncode == RC_UI:
            command = [str(bin_dir.joinpath("provisioner-ui"))]
            continue
        if ps.returncode >= 128:
            print("Exit via signal, exiting (dev)")
            return ps.returncode
    return 0

def entrypoint():
    sys.exit(main())
