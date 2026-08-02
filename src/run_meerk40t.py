#!/usr/bin/env python3
"""MeerK40t launcher with the V1 shim pre-loaded.
Runs without a console (use pythonw.exe). Everything is logged to
logs\\meerk_trace.log in the package root - including failures."""
import faulthandler
import os
import sys
import time
import traceback

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)   # next to the .exe
    ROOT = APP_DIR
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "meerk_trace.log")

__version__ = "1.1.0"

# capture crashes + stderr into the log (no console in frozen mode)
try:
    _f = open(LOG, "a")
    faulthandler.enable(file=_f)
    sys.stderr = _f
except Exception:
    pass

def _excepthook(t, v, tb):
    try:
        with open(LOG, "a") as f:
            f.write("UNCAUGHT EXCEPTION:\n")
            traceback.print_exception(t, v, tb, file=f)
    except Exception:
        pass

sys.excepthook = _excepthook


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def main():
    log("=== MeerK40t V1 launch %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        import libusb_bootstrap  # noqa: F401
        import v1_meerk40t
        log("V1 shim loaded")
    except Exception as e:
        log(f"SHIM LOAD FAILED: {e}")
        traceback.print_exc()
        return 1
    try:
        import meerk40t.main
        log("starting GUI (pythonw, no console)")
        meerk40t.main.run()
        log("GUI exited")
    except Exception as e:
        log(f"GUI ERROR: {e}")
        traceback.print_exc()
        return 2
    return 0


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(f"run_meerk40t {__version__}")
        sys.exit(0)
    sys.exit(main())
