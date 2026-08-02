# Building the release package

Two ways to get a release package:

1. **From a GitHub release** - the pre-built `setup/` folder as a zip, ready
   to hand over as a folder. No tools needed.
2. **From source** - run the build script yourself. This is also what the
   GitHub Actions workflow does on every version tag.

## Prerequisites (build machine)

- Windows 10/11 x64
- Python 3.12 x64 on PATH
- Internet on the **first** build (downloads are cached afterwards)

```bash
pip install -r tools/requirements-build.txt
```

## Build

```bash
python tools/build_release.py
```

What it does:

1. downloads the pinned Python embeddable and get-pip.py into
   `tools/.cache/`, each verified against a pinned SHA-256
   (downloads only once - later runs are offline)
2. downloads the pinned wheels into `tools/.cache/wheelhouse/`
3. builds `MeerK40t-V1.exe` and `SetupPanel.exe` with PyInstaller from the
   committed specs
4. assembles everything into `setup/` - the complete package folder

```bash
python tools/build_release.py --no-exes   # just re-assemble from dist/
python tools/build_release.py --refresh   # force wheelhouse re-download
```

Result: `setup/` is the entire product. Zip it for distribution; end
users extract it and run `SetupPanel.exe` (see `installer/STEPS.md`).

## Layout of the assembled package

```
setup/  (= the release zip)
├── SetupPanel.exe / MeerK40t-V1.exe     the apps (run SetupPanel.exe first)
├── README.md / STEPS.md                 end-user docs
├── app/                                 shims + USB stack (runs in place)
├── scripts/                             install.bat, bind_winusb.cmd,
│                                        run_meerk40t.cmd, selftest.cmd,
│                                        diag.cmd
├── tools/                               zadig.exe (WinUSB driver tool)
├── config/                              MeerK40t.cfg (device config)
├── tests/                               selftest.py / diag_info.py
├── data/                                v1_upload_sequence.dat (firmware)
├── offline/                             bundled Python + pip + wheelhouse/
│                                        (only the installer reads this)
├── runtime/                             bundled Python, created at install
└── logs/                                every log the scripts produce
```

## Version bumps

All version pins live in `tools/`:

| File | What it pins |
|---|---|
| `tools/requirements-runtime.txt` | the 19 runtime packages (bundled in the package) |
| `tools/requirements-build.txt` | PyInstaller |
| `tools/build_release.py` | Python embed version + SHA-256s, PyInstaller version |

Bump the version number in the `__version__` strings (`src/*.py`,
`installer/SetupPanel.py`, `tests/selftest.py`) and `tools/build_release.py`
together.

## Upgrading to a newer MeerK40t

The shim patches MeerK40t's internal balormk fork, so a new MeerK40t can
silently change assumptions. The safe procedure:

1. bump `meerk40t` in `tools/requirements-runtime.txt`
2. rebuild the wheelhouse: `python tools/build_release.py --refresh`
3. install the new MeerK40t into a scratch venv, run
   `tests/test_v1_galvoplotter_mock.py` (offline, catches API drift)
4. with a board attached: `tests/selftest.py` (5/5), then
   `tests/test_capabilities.py` - the full list of every command/record
   the shim can emit
5. diff `v1_meerk40t.py` against the new balormk source in the venv
   (`site-packages/meerk40t/balormk/`): look for new commands the driver
   might now emit (new settings, new record types)
6. only then tag a release

Never bump without running step 4 - the capability test is the regression
safety net.

## GitHub Actions (from the second release onward)

Push a `v*` tag and the workflow `.github/workflows/release.yml` does the
whole thing on a fresh Windows runner: install build deps, build, run the
offline CI test (`tests/ci_test.py` - no board needed), and attach the
assembled `setup/` zip to the GitHub Release for that tag.

The first release is built locally with `tools/build_release.py` so the
workflow itself is verified against a known-good artifact.
