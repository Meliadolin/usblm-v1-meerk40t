#!/usr/bin/env python3
"""Make libusb-1.0.dll loadable - MUST be imported before usb.core.

Why this is needed (fresh PC):
- pyusb's libusb1 backend locates the DLL via ctypes.util.find_library(),
  which on Windows searches next to python.exe and PATH only - it does
  NOT search os.add_dll_directory() folders.
- os.add_dll_directory() alone makes ctypes.WinDLL('libusb-1.0.dll')
  work, but find_library() still returns None -> the backend fails to
  load SILENTLY -> usb.core.find() enumerates 0 devices -> the board
  looks "not present" even though Windows has it bound to WinUSB.

Fix (both mechanisms, belt and suspenders):
1. Prepend the DLL folder to PATH (so find_library finds it)
2. Shim ctypes.util.find_library to return our DLL deterministically
"""
import ctypes.util
import os
import sys

__version__ = "1.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))

_candidates = [
    os.path.join(HERE, "libusb-1.0.dll"),                 # next to this file
    os.path.join(os.path.dirname(sys.executable),         # next to python.exe
                 "libusb-1.0.dll"),
    os.path.join(os.path.dirname(sys.executable), "DLLs",
                 "libusb-1.0.dll"),
]

_DLL_PATH = None
for _c in _candidates:
    if os.path.exists(_c):
        _DLL_PATH = _c
        try:
            os.add_dll_directory(os.path.dirname(_c))
        except Exception:
            pass
        # PATH prepend: makes ctypes.util.find_library() find it
        try:
            _dir = os.path.dirname(_c)
            os.environ["PATH"] = _dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass
        break

if _DLL_PATH:
    _orig_find_library = ctypes.util.find_library

    def _v1_find_library(name):
        if name in ("usb-1.0", "libusb-1.0", "libusb", "usb"):
            return _DLL_PATH
        return _orig_find_library(name)

    ctypes.util.find_library = _v1_find_library
