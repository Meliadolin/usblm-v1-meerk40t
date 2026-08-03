# Third-party components

Everything in this repository and in the pre-built release packages that is
not this project's code, and what license applies to it. All of these are
free to redistribute; the release packages ship the license texts with
them where required.

## Bundled in the release package (runtime)

| Component | Version | License | Notes |
|---|---|---|---|
| MeerK40t | 0.9.9100 | MIT | The GUI/marking application this project extends |
| galvoplotter | 0.2.0 | MIT | Board communication layer (standalone lib; the shim also patches MeerK40t's embedded balormk fork) |
| wxPython | 4.2.2 | wxWindows Library Licence | GUI toolkit (LGPL-compatible) |
| pyusb | 1.3.1 | BSD-3-Clause | USB access |
| libusb-1.0.dll | 1.0.x | LGPL-2.1-or-later | Dynamically loaded, not linked in |
| numpy | 2.5.1 | BSD-3-Clause | |
| pillow | 12.3.0 | MIT-CMU (HPND) | |
| ezdxf | 1.4.4 | MIT | DXF import |
| pyserial | 3.5 | BSD-3-Clause | |
| fonttools | 4.63.0 | MIT | |
| chardet | 7.4.3 | LGPL-2.1 | |
| colorama | 0.4.6 | BSD-3-Clause | |
| packaging | 26.2 | Apache-2.0 / BSD-2-Clause | |
| pyparsing | 3.3.2 | MIT | |
| six | 1.17.0 | MIT | |
| typing_extensions | 4.16.0 | PSF-2.0 | |
| pkg_about | 2.4.3 | BSD-3-Clause | |
| py_utlx | 2.4.0 | BSD-3-Clause | |
| pyproject_hooks | 1.2.0 | MIT | |
| build | 1.5.0 | MIT | |
| python-embed.zip | 3.12.10 | PSF-2.0 | Embeddable CPython runtime |
| Zadig | 2.9 | GPL-3.0-or-later | Signed driver installer - binds the board to WinUSB (`zadig.exe` ships in the package; read-only at runtime) |

## Build tools

| Component | Version | License | Notes |
|---|---|---|---|
| PyInstaller | 6.21.0 | GPL-2.0-or-later with bootloader exception | The exception explicitly allows bundling any program in the produced executables |

## The JCZ firmware image (`data/v1_upload_sequence.dat`)

This file is **not** this project's code and is **not** open source. It is
the boot firmware image that JCZ's official `LMCUSB.sys` Windows driver
uploads to USBLM-V1 boards on every plug-in, replayed by
`upload_firmware.py` instead of the vendor driver.

It is bundled because the board is useless without it: the board's ROM
loader (PID 9990) only accepts this exact image, and JCZ provides no
downloadable copy. If you are JCZ and want it taken down, open an issue and
it will be removed immediately.

## Reverse-engineering material

The protocol documentation (`docs/PROTOCOL.md`) was derived from:
- USB captures of EZCAD 2.5.3 (the vendor's own Windows software)
- The public open-source `galvoplotter` library (MIT), whose command
  constants were cross-checked against the captures
- Live tests on the physical board

No vendor binary or source was included in the documentation process
beyond observing what EZCAD sends over USB.
