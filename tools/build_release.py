#!/usr/bin/env python3
"""Build the offline release package into setup/.

What this does, in order:
  1. Cache third-party downloads (python embed, get-pip) under
     tools/.cache - verified against pinned SHA-256 hashes. Downloads
     only on the first run; later runs work offline.
  2. Fill the wheelhouse (pip download, pinned versions) if missing.
  3. Build the two onefile executables with PyInstaller from the specs.
  4. Assemble the complete setup/ package: installer scripts, the profile,
     firmware, docs.

Run from the repository root:
    python tools\\build_release.py            # full build
    python tools\\build_release.py --no-exes  # package only, skip exes

Requirements on the build machine:
    - Windows 10/11 x64, Python 3.12 x64
    - pip install -r tools\\requirements-build.txt
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "setup")
CACHE = os.path.join(ROOT, "tools", ".cache")
DIST = os.path.join(ROOT, "dist")

VERSION = "1.1.0"

PYTHON_EMBED = {
    "file": "python-embed.zip",
    "url": "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
    "sha256": "4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3",
}
GET_PIP = {
    "file": "get-pip.py",
    "url": "https://bootstrap.pypa.io/get-pip.py",
    "sha256": "25B5C39ADE96BAB5EABE6404CE83CAB6DA2DEB5FE3C07D9881F43803EDB6F9C8",
}
PYINSTALLER = "6.21.0"

# Zadig installs the WinUSB driver (the board's INF cannot be signed;
# pnputil rejects unsigned INFs, so the signed zadig.exe is the driver path).
ZADIG = {
    "file": "zadig.exe",
    "url": "https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe",
    "sha256": "4ECAA95DF3DA3621486A043AEF8B3050B8BAFE7C901402871E816229EF82039B",
}

# wheelhouse source list: tools/requirements-runtime.txt

# Package layout (what ends up in setup/, = the release zip):
#   root:     the apps (SetupPanel.exe, MeerK40t-V1.exe) + the two docs
#   app/:     the USBLM-V1 profile + USB stack (runs in place from the package)
#   scripts/: the install/launch/driver/verification scripts
#   tools/:   zadig.exe (signed WinUSB driver tool)
#   config/:  MeerK40t.cfg (deployed to the standard MeerK40t location)
#   tests/:   verification tools (run by scripts/selftest.cmd etc.)
#   data/:    firmware image
#   offline/: the bundled Python + pip + wheels (only the installer reads it)
#   runtime/: extracted bundled Python (created at install time)
#   logs/:    every log the panel and the scripts produce
PACKAGE_ROOT_FILES = [
    "installer/README.md", "installer/STEPS.md",
]

PACKAGE_SCRIPTS_FILES = [
    "installer/install.bat", "installer/bind_winusb.cmd",
    "installer/run_meerk40t.cmd", "installer/selftest.cmd",
    "installer/diag.cmd",
]

PACKAGE_CONFIG_FILES = [
    "installer/MeerK40t.cfg",
]

PACKAGE_APP_FILES = [
    "src/run_meerk40t.py", "src/v1_galvoplotter.py",
    "src/upload_firmware.py", "src/libusb_bootstrap.py",
    "src/libusb-1.0.dll",
]

PACKAGE_APP_DIRS = [
    "src/usblm_v1",
]

PACKAGE_TEST_FILES = [
    "tests/selftest.py", "tests/diag_info.py",
]

PACKAGE_DATA_FILES = [
    "data/v1_upload_sequence.dat",
]


def log(msg):
    print(f"[build] {msg}")


def fail(msg):
    print(f"[build] FAIL: {msg}")
    sys.exit(1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def cached_download(spec):
    """Download into tools/.cache if missing or hash-mismatched; verify hash."""
    target = os.path.join(CACHE, spec["file"])
    if os.path.exists(target):
        if sha256(target) == spec["sha256"]:
            log(f"{spec['file']}: cached, hash OK")
            return target
        log(f"{spec['file']}: hash mismatch, re-downloading")
    os.makedirs(CACHE, exist_ok=True)
    log(f"downloading {spec['url']}")
    urllib.request.urlretrieve(spec["url"], target)
    if sha256(target) != spec["sha256"]:
        os.remove(target)
        fail(f"{spec['file']}: SHA-256 mismatch after download "
             f"(expected {spec['sha256']})")
    log(f"{spec['file']}: downloaded + verified")
    return target


def check_pyinstaller():
    if not shutil.which("python"):
        fail("python not found on PATH")
    out = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        fail("PyInstaller not installed - run: "
             "pip install -r tools\\requirements-build.txt")
    got = out.stdout.strip()
    if got != PYINSTALLER:
        log(f"WARNING: PyInstaller {got} installed, pinned is {PYINSTALLER}")
    return got


def check_runtime_deps():
    """PyInstaller bundles whatever the build interpreter can import.

    The spec files only describe the bundle; if meerk40t/wxPython/pyusb
    are not installed in the build environment the exes come out without
    them and 'build' still reports success. Fail early instead.
    """
    probe = (
        "import importlib.util\n"
        "mods = ['meerk40t', 'wx', 'usb', 'PIL', 'ezdxf', 'numpy']\n"
        "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
        "if missing:\n"
        "    print('missing: ' + ', '.join(missing))\n"
        "    raise SystemExit(1)\n"
    )
    r = subprocess.run([sys.executable, "-c", probe],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"runtime deps missing for PyInstaller ({r.stdout.strip()}) - "
             "run: pip install -r tools\\requirements-runtime.txt")
    log("runtime deps present (meerk40t, wx, pyusb, pillow, ezdxf, numpy)")


def build_wheelhouse(refresh=False):
    wh = os.path.join(CACHE, "wheelhouse")
    if os.path.isdir(wh) and not refresh:
        n = len([f for f in os.listdir(wh) if f.endswith(".whl")])
        log(f"wheelhouse: {n} wheels cached (use --refresh to rebuild)")
        return
    log("wheelhouse: pip download (pinned versions)...")
    if os.path.isdir(wh):
        shutil.rmtree(wh)
    os.makedirs(wh)
    r = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--only-binary=:all:",
         "-r", os.path.join(ROOT, "tools", "requirements-runtime.txt"),
         "-d", wh], cwd=ROOT)
    if r.returncode != 0:
        fail("wheelhouse download failed (network needed on first build)")
    log("wheelhouse: done")


def build_exes():
    for spec in ["MeerK40t-V1.spec", "SetupPanel.spec"]:
        log(f"PyInstaller: {spec}")
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             os.path.join("tools", spec)], cwd=ROOT)
        if r.returncode != 0:
            fail(f"{spec} build failed")


def assemble():
    if os.path.isdir(SETUP):
        shutil.rmtree(SETUP)
    os.makedirs(SETUP)
    for sub in ("app", "scripts", "tools", "config", "tests", "data",
                "logs", "offline"):
        os.makedirs(os.path.join(SETUP, sub))

    for rel in PACKAGE_ROOT_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            fail(f"missing source file: {rel}")
        shutil.copy2(src, SETUP)
    for rel in PACKAGE_SCRIPTS_FILES:
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(SETUP, "scripts"))
    for rel in PACKAGE_CONFIG_FILES:
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(SETUP, "config"))
    for rel in PACKAGE_APP_FILES:
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(SETUP, "app"))
    for rel in PACKAGE_APP_DIRS:
        src = os.path.join(ROOT, rel)
        if not os.path.isdir(src):
            fail(f"missing source dir: {rel}")
        shutil.copytree(src, os.path.join(SETUP, "app", os.path.basename(rel)))
    for rel in PACKAGE_TEST_FILES:
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(SETUP, "tests"))
    for rel in PACKAGE_DATA_FILES:
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(SETUP, "data"))

    for spec in ["python-embed.zip", "get-pip.py"]:
        shutil.copy2(os.path.join(CACHE, spec), os.path.join(SETUP, "offline"))
    shutil.copytree(os.path.join(CACHE, "wheelhouse"),
                    os.path.join(SETUP, "offline", "wheelhouse"))
    shutil.copy2(os.path.join(CACHE, ZADIG["file"]),
                 os.path.join(SETUP, "tools"))

    for exe in ["MeerK40t-V1.exe", "SetupPanel.exe"]:
        src = os.path.join(DIST, exe)
        if not os.path.exists(src):
            fail(f"missing built exe: {src} (run without --no-exes)")
        shutil.copy2(src, SETUP)

    log("assemble: done")


def verify_package():
    def size(path):
        return os.path.getsize(path) // (1024 * 1024)

    exe_m = size(os.path.join(SETUP, "MeerK40t-V1.exe"))
    panel_m = size(os.path.join(SETUP, "SetupPanel.exe"))
    if exe_m < 20:
        fail(f"MeerK40t-V1.exe is only {exe_m} MB - the runtime stack "
             "(meerk40t/wxPython/pyusb) was not bundled. Install "
             "tools/requirements-runtime.txt and rebuild.")
    if panel_m < 5:
        fail(f"SetupPanel.exe is only {panel_m} MB - build is incomplete.")
    wheels = len([f for f in os.listdir(os.path.join(SETUP, "offline",
                                                      "wheelhouse"))
                  if f.endswith(".whl")])
    scripts = len([f for f in os.listdir(os.path.join(SETUP, "scripts"))
                   if f.endswith((".bat", ".cmd"))])
    if scripts != 5:
        fail(f"expected 5 scripts in setup/scripts/, found {scripts}")
    log("=" * 60)
    log("PACKAGE VERIFIED")
    log(f"  MeerK40t-V1.exe : {exe_m} MB")
    log(f"  SetupPanel.exe   : {panel_m} MB")
    log(f"  wheelhouse       : {wheels} wheels")
    log(f"  python-embed.zip : {size(os.path.join(SETUP, 'offline', 'python-embed.zip'))} MB")
    log(f"  zadig.exe         : {size(os.path.join(SETUP, 'tools', 'zadig.exe'))} MB")
    total = sum(size(os.path.join(SETUP, f))
                for f in os.listdir(SETUP) if os.path.isfile(os.path.join(SETUP, f)))
    log(f"  package root     : ~{total} MB (excl. subfolders)")
    log("  => the setup/ folder is the complete package: run SetupPanel.exe")
    log("=" * 60)


def main():
    ap = argparse.ArgumentParser(description="Build the offline release package")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the wheelhouse")
    ap.add_argument("--no-exes", action="store_true",
                    help="skip PyInstaller (reuse existing dist/ exes)")
    ap.add_argument("--version", action="version", version=f"build_release {VERSION}")
    args = ap.parse_args()

    log(f"usblm-v1-meerk40t release build v{VERSION}")

    cached_download(PYTHON_EMBED)
    cached_download(GET_PIP)
    cached_download(ZADIG)
    build_wheelhouse(refresh=args.refresh)
    if not args.no_exes:
        check_pyinstaller()
        check_runtime_deps()
        build_exes()
    assemble()
    verify_package()


if __name__ == "__main__":
    main()
