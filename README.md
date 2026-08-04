# usblm-v1-meerk40t

Makes the BJJCZ "USBLM-V1" galvo board (VID_9588 / PID_9999) run as a
native device in [MeerK40t](https://github.com/meerk40t/meerk40t) on
64-bit Windows 10/11.

## What this is

The V1 board was sold with EZCAD, JCZ's closed Windows-only marking software.
EZCAD only runs on 32-bit Windows with JCZ's kernel driver and a hardware
license dongle, so the board has effectively been unusable on Windows 10/11
x64 except inside an old OS VM.

This project removes that dependency. It contains:

- a USB controller for the V1 board, driven purely in userspace through
  pyusb/libusb (WinUSB driver; no kernel vendor driver involved),
- automatic firmware upload: the board enumerates as a loader (PID 9990)
  and needs its firmware loaded before it becomes the marking device
  (PID 9999),
- a native MeerK40t device profile (`src/usblm_v1/`) that speaks the V1
  wire protocol directly - the board shows up in the GUI as its own
  device (USBLM-V1), next to the stock balormk devices,
- a GUI setup panel (`SetupPanel.exe`) that installs everything on a fresh
  PC,
- hardware tests and a self-test, plus the full protocol documentation.

The wire protocol was reverse-engineered from USB captures of EZCAD 2.5.3
driving the board; `docs/REVERSE_ENGINEERING.md` documents how.

## Status

Verified on the physical board through the MeerK40t GUI:
marking, multi-direction fills, raster engraving, red-light trace and
live-outline. The board's quirks (chunked job lists, buffered execution,
paused-state behaviour on StopList, firmware reload after a USB bus reset)
are handled in the profile and documented in `docs/PROTOCOL.md`.

## For users: the package

The release packages are published in the GitHub Releases of this repo.
Download the zip, extract it, and run `SetupPanel.exe` from the extracted
folder:

1. **Install Software** - installs Python, all packages and
   device settings.
2. **Install USB Driver** - binds the board to WinUSB with the signed
   `zadig.exe` that ships in the package (one permission prompt - click
   Yes; in the Zadig window pick "USBLM-V1" and click Install Driver).
   The board re-enumerates afterwards (briefly disappears/reappears) -
   normal.
3. **Run Self-Test** - expect `5 passed, 0 failed`.
4. **Launch MeerK40t** - start marking.

Full end-user instructions: `installer/STEPS.md`. The pre-configured laser
power is **30%**.

## For developers

```bash
# From source
pip install pyusb libusb meerk40t wxPython ezdxf pillow numpy
python src/run_meerk40t.py                 # GUI with the profile registered

# Hardware self-test (no laser fires)
python tests/selftest.py                   # expect 5/5 PASS
```

```python
# Library use
from v1_controller import V1Controller
ctrl = V1Controller()
ctrl.connect()          # auto-uploads firmware if the board is in loader mode
ctrl.init()
ctrl.goto(0x8000, 0x8000)
ctrl.mark([(0x6000, 0x6000), (0xA000, 0x6000)])   # 0x8000 = field center
```

### Repository layout

```
src/             the USB controller, the USBLM-V1 MeerK40t profile,
                 and the galvoplotter profile
installer/       everything that becomes the package: SetupPanel source,
                 install/driver/launch scripts, config, end-user docs
tests/           hardware tests, mock tests, selftest, CI test
tools/           build_release.py + PyInstaller specs (makes the package)
docs/            protocol, reverse engineering guide, build guide
data/            firmware image + verified protocol reference
```

The released package (`setup/`, built by `tools/build_release.py`) is
fully self-contained: the apps and docs at the top level, everything
else in subfolders. Nothing is written outside the package except the
device settings in the standard MeerK40t location:

```
setup/
├── SetupPanel.exe / MeerK40t-V1.exe    the apps (run SetupPanel.exe first)
├── README.md / STEPS.md                end-user docs
├── app/     USBLM-V1 profile + USB stack (runs in place from this folder)
├── scripts/ install.bat, bind_winusb.cmd, run_meerk40t.cmd,
│            selftest.cmd, diag.cmd
├── tools/   zadig.exe (signed WinUSB driver tool)
├── config/  MeerK40t.cfg (deployed to the standard MeerK40t location)
├── tests/   selftest.py / diag_info.py
├── data/    v1_upload_sequence.dat (firmware)
├── offline/ bundled Python + pip + wheelhouse (installer-only)
├── runtime/ bundled Python, extracted at install time
└── logs/    every log the panel and the scripts produce
```

### The device profile

`src/usblm_v1/` is a MeerK40t plugin. It registers the V1 board as a
native device provider (`provider/device/usblmv1`) with its own driver,
controller, console commands and GUI panels - stock balormk devices are
untouched, both providers coexist:

- `plugin.py` / `device.py` - kernel registration and the device service
- `driver.py` - the MeerK40t driver interface (subclasses balormk's BalorDriver)
- `controller.py` - the V1 protocol: records, chunks, waits, recovery
- `transport.py` - USB endpoints (EP 0x01/0x81, 3072-byte chunks on EP 0x02)
- `commands.py` - the galvo console commands
- `upstream_patches.py` - two upstream MeerK40t bug fixes (numpy 2 hull,
  stale reference nodes on delete, issue #3253)

The profile is pip-installable into a stock MeerK40t via the
`meerk40t.extension` entry point (`pip install .`); the launcher
(`src/run_meerk40t.py`) registers it explicitly for the packaged exe.

`src/v1_galvoplotter.py` is the same V1 profile for the standalone
galvoplotter library.

Both implement the same verified V1 wire model: commands on EP 0x01
(14-byte packets with the 0x0002 prefix), 10-byte responses on EP 0x81,
3072-byte list chunks on EP 0x02, the board's chunk-ack drain, the
buffered job model (queue all chunks, then execute once), and auto
firmware upload from loader mode (PID 9990).

### Documentation

- `docs/PROTOCOL.md` - the full verified wire protocol
- `docs/REVERSE_ENGINEERING.md` - how the protocol was captured and decoded
- `docs/BUILDING.md` - build the offline package from source
- `docs/TROUBLESHOOTING.md` - what to do when something doesn't work
- `docs/LINUX.md` - running on Linux/Mac (works; no driver step)

## License

MIT. Third-party components and the JCZ firmware image are
covered in [THIRD_PARTY.md](THIRD_PARTY.md).
