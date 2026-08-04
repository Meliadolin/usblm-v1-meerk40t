#!/usr/bin/env python3
"""Self-test for the MeerK40t V1 setup on any PC.
Verifies: profile loads, board found, firmware upload works, board responds,
galvo can move (no laser). Run BEFORE using the GUI."""
import os
import struct
import sys
import time

__version__ = "1.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
# dev layout: the profile + USB stack live in src/ ; shipped: in app/
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import libusb_bootstrap  # noqa: F401 - must be before usb.core

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "selftest_log.txt")


def _log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
        _log(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")
        _log(f"FAIL: {name} {detail}")


def main():
    print("=== USBLM-V1 + MeerK40t self-test ===\n")

    # 1. profile loads
    try:
        import usblm_v1  # noqa: F401
        check("profile import", True)
    except Exception as e:
        check("profile import", False, str(e))
        return 1

    # 2. libusb + board presence
    try:
        import usb.core
        dev = usb.core.find(idVendor=0x9588, idProduct=0x9999)
        loader = usb.core.find(idVendor=0x9588, idProduct=0x9990)
        if dev:
            check("board found (PID 9999)", True)
        elif loader:
            check("board in loader mode (PID 9990) - auto-upload will handle it", True)
        else:
            # not visible to libusb - scan the Windows side for the truth
            _log("board not visible to libusb - scanning Windows device tree:")
            print("  (libusb sees nothing - checking Windows device tree...)")
            try:
                from usblm_v1.transport import scan_windows_usb
                scan_windows_usb()
            except Exception as e:
                _log(f"  windows scan failed: {e}")
            check("board found", False, "- see v1_shim_trace.log for the Windows-side scan")
            return 1
    except Exception as e:
        check("pyusb/libusb", False, str(e))
        return 1

    # 3. full connect + init (uploads firmware if needed, no laser)
    from usblm_v1.controller import V1Controller

    try:
        from test_v1_meerk40t_real import FakeService  # reuse the fake service
    except ImportError:

        class FakeChannel:
            _ = staticmethod(lambda s: s)

            def watch(self, *a, **k):
                pass

            def __call__(self, *a, **k):
                pass

        class FakeService:
            safe_label = "V1TEST"
            source = "fiber"
            signal_updates = False
            corfile = None
            corfile_enabled = False
            serial_enable = False
            serial = None
            delay_openmo = 8.0
            first_pulse_killer = 200
            pwm_pulse_width = 125
            pwm_half_period = 125
            standby_param_1 = 2000
            standby_param_2 = 20
            timing_mode = 1
            delay_mode = 1
            laser_mode = 1
            control_mode = 0
            fpk2_p1, fpk2_p2, fpk2_p3, fpk2_p4 = 0x0FFB, 1, 0x0199, 100
            fly_res_p1, fly_res_p2, fly_res_p3, fly_res_p4 = 0, 99, 1000, 25
            _settings = {"light_pin": 8, "foot_pin": 15}

            def setting(self, typ, name, default=None):
                return self._settings.get(name, default)

            def channel(self, *a, **k):
                return FakeChannel()

            def signal(self, *a, **k):
                pass

            class _View:
                @staticmethod
                def position(*a, **k):
                    return (10.0, 10.0)

            view = _View()

    ctrl = None
    try:
        ctrl = V1Controller(FakeService())
        ctrl.connect_if_needed()
        check("connect + init (firmware upload if needed)", True)
        st = ctrl.status()
        check("board status readback", st is not None, f"state={hex(st) if st else None}")

        # galvo movement test (laser OFF - program_mode closes MO after)
        ctrl.program_mode()
        # full settings records (mirrors what the MeerK40t driver writes)
        ctrl.list_jump_speed(0x0D1B)      # jump speed 3355
        ctrl.list_mark_speed(0x0320)      # mark speed 800
        ctrl.list_mark_current(0x0064)    # power ~10%
        ctrl.list_qswitch_period(0x03E8)  # frequency 20kHz
        ctrl.list_laser_on_delay(0x012C)
        ctrl.list_laser_off_delay(0x0064)
        ctrl.list_polygon_delay(0x000A)
        ctrl.list_jump_delay(0x0064)
        ctrl.goto(0x7000, 0x7000)
        ctrl.mark(0x9000, 0x7000)
        ctrl.mark(0x9000, 0x9000)
        ctrl.mark(0x7000, 0x9000)
        ctrl.mark(0x7000, 0x7000)
        ctrl.rapid_mode()
        st = ctrl.status()
        check("galvo move + idle (0x0220)", st == 0x0220,
              f"state={hex(st) if st else None}")
        ctrl.disconnect()
    except Exception as e:
        check("controller flow", False, str(e))
        try:
            ctrl and ctrl.disconnect()
        except Exception:
            pass

    print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
    if FAIL == 0:
        print("Setup is GOOD - start MeerK40t via run_meerk40t.cmd")
    else:
        print("Fix the failures above, then rerun.")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(f"selftest {__version__}")
        sys.exit(0)
    sys.exit(main())
