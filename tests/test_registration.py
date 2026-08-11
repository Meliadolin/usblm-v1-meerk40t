#!/usr/bin/env python3
"""Offline device-provider registration test - no board, no GUI.

Verifies the exact runtime path of run_meerk40t.py: with the launcher's
internal_plugins wrapper installed, the USBLM-V1 provider registers with
a bare kernel ('provider/device/usblmv1'), the device constructs with the
V1 driver/controller, and the console/gui plugin hooks attach cleanly.

Notes:
- Requires a meerk40t install (entry points of the real GUI are not
  involved; this is the frozen-exe registration path).
- meerk40t's potrace plugin uses an numba @njit(cache=True) that hangs
  on some machines unless JIT is disabled and temp/cache dirs are pinned
  (stock kernel hangs identically without usblmv1 involved). The env
  workaround is applied below BEFORE any meerk40t import.
- sys.excepthook is replaced: meerk40t's wx excepthook would otherwise
  pop blocking dialogs on any verification error.
"""
import os
import sys
import tempfile
import traceback

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
_tmp = os.path.join(tempfile.gettempdir(), "usblmv1_registration")
os.makedirs(_tmp, exist_ok=True)
os.environ["TMP"] = _tmp
os.environ["TEMP"] = _tmp
os.environ["NUMBA_CACHE_DIR"] = os.path.join(_tmp, "numba_cache")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
sys.path.insert(0, SRC)

failures = []


def check(name, cond, extra=""):
    print(f"[{'OK' if cond else 'FAIL'}] {name} {extra}", flush=True)
    if not cond:
        failures.append(name)


def hook(t, v, tb):
    print("EXCEPTION:", "".join(traceback.format_exception(t, v, tb)), flush=True)
    sys.exit(3)


sys.excepthook = hook

# 1. package + bundled upstream bugfix patches
import libusb_bootstrap  # noqa: F401
import usblm_v1  # noqa: F401

from meerk40t.core.geomstr import Geomstr
from meerk40t.core.elements.elements import Elemental
import usblm_v1.upstream_patches as up

check("upstream hull patch",
      Geomstr.hull.__func__.__module__ == "usblm_v1.upstream_patches")
check("upstream remove_nodes patch", Elemental.remove_nodes is up._remove_nodes)

# 2. launcher wrapper (exact run_meerk40t.py logic)
import meerk40t.internal_plugins as _ip

_orig_internal_plugins = _ip.plugin


def _plugin_with_usblmv1(kernel, lifecycle):
    if lifecycle == "plugins":
        from usblm_v1.plugin import plugin as usblmv1_plugin
        kernel.add_plugin(usblmv1_plugin)
    return _orig_internal_plugins(kernel, lifecycle)


_ip.plugin = _plugin_with_usblmv1

# 3. kernel + register lifecycle
from meerk40t.kernel import Kernel
from meerk40t.kernel.lifecycles import (
    LIFECYCLE_KERNEL_REGISTER,
    LIFECYCLE_KERNEL_PREBOOT,
    LIFECYCLE_KERNEL_BOOT,
)
import meerk40t.main as _mk_main

k = Kernel("meerk40t", "0.9.9100", "meerk40t")
k.args = _mk_main.parser.parse_args(["-z"])
k.add_plugin(_ip.plugin)
k.set_kernel_lifecycle(k, LIFECYCLE_KERNEL_REGISTER)
k.set_kernel_lifecycle(k, LIFECYCLE_KERNEL_PREBOOT)
k.set_kernel_lifecycle(k, LIFECYCLE_KERNEL_BOOT)

from usblm_v1.device import V1Device

check("provider registered", k.lookup("provider/device/usblmv1") is V1Device)
friendly = k.lookup("provider/friendly/usblmv1")
check("friendly registered",
      friendly is not None and friendly[0] == "USBLM-V1", str(friendly))
dev_info = k.lookup("dev_info/usblmv1")
check("dev_info registered",
      dev_info is not None
      and dev_info["provider"] == "provider/device/usblmv1")
check("balor untouched", k.lookup("provider/device/balor") is not None)

# 4. device construction
dev = V1Device(k, "usblmv1/0")
check("device label", dev.label == "USBLM-V1", dev.label)
check("driver V1Driver", type(dev.driver).__name__ == "V1Driver")
check("connection V1Controller",
      type(dev.driver.connection).__name__ == "V1Controller")
check("no source attr", not hasattr(dev, "source"))
check("location usb", dev.location() == "usb")
d = dev.get_operation_defaults("engrave")
check("op defaults",
      d["pulse_width_enabled"] is False and d["pulse_width"] == 4
      and d["frequency"] == 30.0 and d["rapid_enabled"] is False)

attrs = [c.get("attr") for c in dev._registered["choices/balor"]]
redlight = [c.get("attr") for c in dev._registered["choices/balor-redlight"]]
check("no source choice", "source" not in attrs)
check("no corfile choices",
      "corfile" not in attrs and "corfile_enabled" not in attrs)
check("no pulse width choices",
      "pulse_width_enabled" not in attrs and "default_pulse_width" not in attrs)
check("key choices present",
      {"light_pin", "mock", "pedal_mode", "lens_size"} <= set(attrs))
check("redlight choices present", "redlight_speed" in redlight)
check("choice count", len(attrs) == 20, f"n={len(attrs)}")

# 5. console commands + gui on the real service
from usblm_v1 import commands, gui

commands.plugin(dev, "added")
gui.plugin(dev, "added")
check("commands service key",
      commands.plugin(None, "service") == "provider/device/usblmv1")
check("gui service key",
      gui.plugin(None, "service") == "provider/device/usblmv1")

print("FAILURES:", failures if failures else "none", flush=True)
# os._exit: the kernelserver plugin leaves non-daemon threads behind
# after the boot lifecycle - sys.exit would hang the test.
os._exit(1 if failures else 0)
