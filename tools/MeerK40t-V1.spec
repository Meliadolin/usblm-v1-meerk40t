# -*- mode: python ; coding: utf-8 -*-
# MeerK40t-V1.exe - onefile, windowed. Built by tools/build_release.py.
import os
from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "src", "run_meerk40t.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "src", "libusb-1.0.dll"), "."),
        (os.path.join(ROOT, "data", "v1_upload_sequence.dat"), "data"),
    ] + collect_data_files("meerk40t"),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MeerK40t-V1",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
