#!/usr/bin/env python3
"""Environment + USB snapshot - run before anything else on a new PC.
Writes diag_info.log next to this file with everything needed to
diagnose a failed install/launch WITHOUT asking the user anything."""
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# dev layout: the profile + USB stack live in src/ ; shipped: in app/
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import libusb_bootstrap  # noqa: F401 - MUST be before usb.core

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
OUT = os.path.join(LOG_DIR, "diag_info.log")
lines = []


def log(msg):
    lines.append(msg)


def cmd(c):
    try:
        r = subprocess.run(c, shell=True, capture_output=True, text=True,
                           timeout=60)
        return r.stdout.strip() + r.stderr.strip()
    except Exception as e:
        return f"(cmd failed: {e})"


def main():
    log("=" * 60)
    log(f"DIAG {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    log(f"OS: {platform.platform()} ({platform.machine()})")
    log(f"Python: {sys.version.split()[0]} at {sys.executable}")
    log(f"Script dir: {HERE}")

    log("")
    log("--- package versions (pip) ---")
    pkgs = ["meerk40t", "wxPython", "pyusb", "libusb", "numpy",
            "ezdxf", "pillow"]
    for p in pkgs:
        log(f"  {p}: {cmd(f'{sys.executable} -m pip show {p} | findstr /i version')}")
    log("  wxpython full:")
    log(f"    {cmd(f'{sys.executable} -c \"import wx; print(wx.__version__, wx.version())\"')}")

    log("")
    log("--- USB devices (laser board) ---")
    try:
        import usb.core
        try:
            all_devs = list(usb.core.find(find_all=True))
            log(f"  TOTAL devices visible to libusb: {len(all_devs)}")
            for d in all_devs:
                try:
                    log(f"    VID={d.idVendor:04X} PID={d.idProduct:04X} "
                        f"bus={d.bus} addr={d.address}")
                except Exception:
                    log("    (device with unreadable descriptor)")
        except Exception as e:
            log(f"  full enumeration failed: {e}")
        for pid, name in [(0x9999, "normal"), (0x9990, "loader"),
                          (0x9899, "v2-normal"), (0x9980, "v2-loader")]:
            d = usb.core.find(idVendor=0x9588, idProduct=pid)
            log(f"  PID {pid:04X} ({name}): "
                + (f"FOUND bus={d.bus} addr={d.address}" if d else "not present"))
    except Exception as e:
        log(f"  usb scan failed: {e} (pyusb not installed?)")

    log("")
    log("--- loaded libusb DLL (after enumeration) ---")
    try:
        import ctypes
        import usb.backend.libusb1 as lb1
        lib = getattr(lb1, "_lib", None)
        if lib is not None:
            log(f"  backend _lib: {lib}")
            try:
                log(f"  _name: {lib._name}")
            except Exception:
                pass
        else:
            log("  backend _lib: None (no backend loaded)")
        log(f"  ctypes.find_library('usb-1.0'): "
            f"{ctypes.util.find_library('usb-1.0')}")
        log(f"  ctypes.find_library('libusb-1.0'): "
            f"{ctypes.util.find_library('libusb-1.0')}")
        try:
            h = ctypes.WinDLL("libusb-1.0.dll")
            log(f"  WinDLL('libusb-1.0.dll') OK, handle={h._handle}")
        except Exception as e:
            log(f"  WinDLL('libusb-1.0.dll') FAILED: {e}")
    except Exception as e:
        log(f"  dll probe failed: {e}")

    log("")
    log("--- bound driver per PID (registry) ---")
    try:
        import winreg
        for pid in ["9999", "9990"]:
            base = rf"SYSTEM\CurrentControlSet\Enum\USB\VID_9588&PID_{pid}"
            try:
                k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
                instances = []
                i = 0
                while True:
                    try:
                        instances.append(winreg.EnumKey(k, i))
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(k)
                for inst in instances:
                    try:
                        ik = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                            base + "\\" + inst)
                        svc, _ = winreg.QueryValueEx(ik, "Service")
                        dev = winreg.QueryValueEx(ik, "DeviceDesc")[0]
                        winreg.CloseKey(ik)
                        verdict = "OK for libusb" if svc.lower() in (
                            "winusb", "libusbk") else f"NOT libusb-visible ({svc})"
                        log(f"  PID_{pid} '{dev}' Service={svc} -> {verdict}")
                    except OSError as e:
                        log(f"  PID_{pid}\\{inst}: no Service value ({e})")
            except OSError as e:
                log(f"  PID_{pid}: registry key missing ({e})")
    except Exception as e:
        log(f"  registry scan failed: {e}")

    log("")
    log("--- libusb dll ---")
    for loc in [os.path.join(os.path.dirname(sys.executable), "libusb-1.0.dll"),
                os.path.join(HERE, "libusb-1.0.dll"),
                os.path.join(ROOT, "app", "libusb-1.0.dll"),
                os.path.join(ROOT, "src", "libusb-1.0.dll")]:
        log(f"  {loc}: {'present' if os.path.exists(loc) else 'MISSING'}")

    log("")
    log("--- profile imports ---")
    try:
        import usblm_v1
        log("  usblm_v1: OK")
    except Exception as e:
        log(f"  usblm_v1: FAIL {e}")
    try:
        import v1_galvoplotter
        log("  v1_galvoplotter: OK")
    except Exception as e:
        log(f"  v1_galvoplotter: FAIL {e}")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n(written to {OUT})")


if __name__ == "__main__":
    main()
