# MeerK40t + BJJCZ USBLM-V1 - Portable Package

Free software (MeerK40t, MIT) driving the V1 laser board (VID_9588,
PID_9999) on any modern 64-bit Windows PC. No vendor stack needed: no
JCZ driver, no license dongle, no EZCAD. See STEPS.md for the setup/test
procedure.

## What's in this folder

At the top level: the two apps and the two docs. Everything else lives
in subfolders so the folder stays readable - you only need the top
level.

| File / folder | Purpose |
|---|---|
| `SetupPanel.exe` | The control center: install, driver, self-test, launch (this is what you run first) |
| `MeerK40t-V1.exe` | The marking software with the V1 shim compiled in |
| `README.md` / `STEPS.md` | This file / the step-by-step user guide |
| `app\` | The shim + supporting modules (`v1_meerk40t.py` patches MeerK40t's balormk plugin; `v1_galvoplotter.py`, `upload_firmware.py`, `libusb_bootstrap.py`, `libusb-1.0.dll`) - run in place from this folder |
| `scripts\` | `install.bat` (install software), `bind_winusb.cmd` (WinUSB binding, admin), `run_meerk40t.cmd` (GUI launcher), `selftest.cmd` / `diag.cmd` (verification / diagnostics) |
| `tools\` | `zadig.exe` - signed WinUSB driver tool (GPLv3, from pbatard/libwdi); pre-configured via `zadig.ini` |
| `config\` | `MeerK40t.cfg` - pre-configured device: Galvo-Fiber, fiber source, 30% power defaults (deployed to the standard MeerK40t location at install) |
| `tests\` | `selftest.py` (5-check board/shim verification) + `diag_info.py` (diagnostics) |
| `data\` | `v1_upload_sequence.dat` - the firmware image for `upload_firmware.py` |
| `offline\` | What the installer consumes: bundled Python (`python-embed.zip`, `get-pip.py`) + `wheelhouse\` (all pinned packages) |
| `runtime\` | Bundled Python runtime, extracted at install time |
| `logs\` | Every log: install, driver bind, self-test, diagnostics, the shim trace and the app trace |

## How it works

MeerK40t's balormk plugin speaks the JCZ "V2" wire protocol
(PID 9899, EP 0x02/0x88, 8-byte responses). The V1 board speaks the
same protocol family but V1 wire layout (PID 9999, EP 0x01/0x81,
10-byte responses). The shim translates between them - everything else
is normal MeerK40t.

The shim also:
- Auto-uploads firmware if the board is in loader mode (9990)
- Drains the board's chunk-ack responses (prevents read desync)
- Bounded waits + auto-recovery (cannot hang)
- Self-healing status reads (re-syncs if a stale response slips in)
- Forces fiber source (safe even if device was created as CO2)

## Troubleshooting

| Symptom | Fix |
|---|---|
| selftest "board found" fails | Board unplugged, or WinUSB not bound (STEPS.md step 2) |
| GUI crash on start | Last 10 lines of logs\meerk_trace.log show where |
| Job hangs | Close GUI, check logs\meerk_trace.log, report it |
| Board shows "Unknown Device" | WinUSB binding missing - run `scripts\bind_winusb.cmd` (STEPS.md step 2) |
| pip install fails | No internet / firewall; retry, check logs\install_log.txt |
| Mark looks mirrored/rotated | Device Settings: flip_y / swap_xy (test with a letter) |

## Known limitations

- The official MeerK40t installer cannot host the shim - use this package
  (its `MeerK40t-V1.exe` already includes the shim)
- Raster engraving: supported (EZCAD-style pixel records)
- Lens correction: upload format not yet decoded - geometry slightly
  distorted at field edges only
- Linux/Mac: `pip install meerk40t wxPython pyusb pillow ezdxf libusb`,
  copy the shim files, run - no driver step needed
