# Linux / macOS

The whole stack is userspace USB - no Windows driver involved - so the
source runs on Linux and macOS with plain packages. Only the Windows
release package (`setup/`) is Windows-specific.

## Linux

```bash
# install
sudo apt install python3-pip libusb-1.0-0
pip install meerk40t wxPython pyusb pillow ezdxf numpy

# run from the repo root (or copy src/ next to your script)
python src/run_meerk40t.py
```

### Permissions (udev rule)

By default Linux restricts USB access to root. Create
`/etc/udev/rules.d/99-usblm-v1.rules`:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="9588", MODE="0666"
```

Then reload: `sudo udevadm control --reload && sudo udevadm trigger`.
The board enumerates as vendor 0x9588 with product 0x9999 (normal) or
0x9990 (loader, needs the firmware upload first - the shim does it
automatically).

## macOS

```bash
pip install meerk40t wxPython pyusb pillow ezdxf numpy
python src/run_meerk40t.py
```

macOS has no driver-binding step for libusb devices; the board works as-is.
If the firmware upload fails on first connect, replug the board and retry.

## Same protocol, same limits

The wire protocol, the buffered job model and the shim behavior are
identical across platforms - see `docs/PROTOCOL.md`.
