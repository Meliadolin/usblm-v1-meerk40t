#!/usr/bin/env python3
"""MeerK40t launcher with the USBLM-V1 profile registered.
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
        import usblm_v1  # noqa: F401 - applies the bundled upstream bugfix patches
        # Frozen (PyInstaller) builds skip meerk40t's external_plugins entry
        # points, so the V1 provider is injected into the internal plugin
        # list before meerk40t.main imports it (function-level import in
        # _exe()). Source installs register through the pip entry point
        # instead; a duplicate registration is harmless.
        import meerk40t.internal_plugins as _ip
        _orig_internal_plugins = _ip.plugin

        def _plugin_with_usblmv1(kernel, lifecycle):
            if lifecycle == "plugins":
                from usblm_v1.plugin import plugin as usblmv1_plugin
                kernel.add_plugin(usblmv1_plugin)
            return _orig_internal_plugins(kernel, lifecycle)

        _ip.plugin = _plugin_with_usblmv1
        log("USBLM-V1 profile registered")
    except Exception as e:
        log(f"V1 PROFILE LOAD FAILED: {e}")
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
