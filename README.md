# provisioner

Kiwix Hotspot H1 provisioning tool

[![CodeFactor](https://www.codefactor.io/repository/github/offspot/provisioner/badge)](https://www.codefactor.io/repository/github/offspot/provisioner)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![codecov](https://codecov.io/gh/offspot/provisioner/branch/main/graph/badge.svg)](https://codecov.io/gh/openzim/_python-bootstrap)
![PyPI - Python Version](https://img.shields.io/badge/python-3.11-blue)

## What's this?

This is the Python App that is ran by [ProvisionOS](https://github.com/offspot/provision-os/).

It's goal is to *simplify* the process of *provisioning* a Kiwix Hotspot H1.
We call *provisioning* the act of flashing a Kiwix Hotspot OS onto the disk and making some other adjustments.

Most likely **you don't need this tool** as this is specific to the H1 device and process.
It's only useful for those flashing Kiwix Hotspot in a row from a batch of pre-assembled devices.

Feel free to use and customize it though 😊. You're welcome to contribute as well ([contributing guidelines](https://github.com/openzim/overview/wiki/Contributing)).

## Usage

> [!NOTE]
> It only works on Kiwix Hotspot H1 (Pi 5 with NVME disk) running ProvisionOS.

```sh
# ProvisionOS runs
❯ provisioner-script

# without the wrapper that handles shutdown/restart
❯ provisioner-ui
```

## Design

The provisioner app is composed of several components:

- The Terminal UI called “regular mode” (TUI)
- The Command Line Interface called “advanced mode” (CLI)
- A number of probes gathering information from running system/device.
- A number of provision steps performing actual provisioning actions.

ProvisionOS starts `provision-script` which is a wrapper over `provision-ui`. UI allows shutting down or restarting the device. This actually only triggers exit with specific exit-codes understood by `provision-script`, triggering actual reboot/shutdown.

### Host details

`PriovisionHost` and it's `query_*` methods reads status from underlying tools. It's essential for provisioning but takes a lot of time (~15s).
The longest operations being the disk ones because candidate disks are walked through to find images and images are attached, mounted, peeked-at then unmounted/detached.

`provision-status` displays most of them.

### TUI

TUI is implemented in `tui.app.App` using [`urwid`](https://urwid.readthedocs.io/). The `App` keeps the urwid loop alive and records the `ProvisionHost`.

Logical blocks are implemented as `Pane`s which defines the widget that the app will draw on screen.

### CLI

Advanced tools are implemented as simple text programs. Those rely on [`click`](https://click.palletsprojects.com/) and [`Halo`](https://github.com/manrajgrover/halo).

## Development

Because of the requirement (H1, ProvisionOS), it's easier to work off a real, running device.

To do so, grab the latest [ProvisionOS](), flash it on a USB stick and boot your H1 with it. Then SSH into it

```sh
# change host/IP
❯ ssh kiwix@h1
```

```sh
# switch to root
❯ sudo su -

# install sshfs and uv
❯ python3 -m venv /root/env && apt update && apt install -y sshfs curl && curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env && source /root/env/bin/activate && mkdir -p /root/provisioner

# mount you dev's repo on the Pi [CHANGE THIS]
❯ sshfs USER@DEVHOST:PATHONDEVHOST /root/provisioner && cd /root/provisioner && uv run --active provisioner-ui --help
# ex: sshfs reg@faku.ylm:src/provisioner /root/provisioner && cd /root/provisioner && uv run --active provisioner-ui --help

# then start any of the entrypoints

# similar to provisionOS, restarts when requested
❯ uv run --active provisioner-script

# the UI but shudown/restart just exits
❯ uv run --active provisioner-ui

# advanced mode status
❯ uv run --active provisioner-status

# advanced mode provisioning (you must pass disks and image)
❯ uv run --active provisioner-manual --help
```

To test on the actual screen, change `/root/.bash_profile` to use the dev code:

```sh
# load uv
. "$HOME/.local/bin/env"

# activate env
source /root/env/bin/activate

if [ "$RUNKIOSK" = "1" ]; then
  uv run --active provisioner-script
fi
```

Then restart the Kiosk service

```sh
systemctl restart kiosk.service
```