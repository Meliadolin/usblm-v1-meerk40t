#!/usr/bin/env python3
"""CAPABILITY TEST v2 - properly isolated.
Order: light mode -> realtime commands -> list records (via shim flow,
auto-recovery) -> axis commands LAST (they set the AXIS state flag).
No laser power anywhere (mark current 0, MO closed after each run)."""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import libusb_bootstrap  # noqa: F401

from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "capability_test.log")
lines = []


def log(msg):
    print(msg)
    lines.append(msg)


def main():
    log("=" * 60)
    log(f"CAPABILITY TEST v2 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    ctrl = V1Controller(FakeService())
    try:
        ctrl.connect_if_needed()
        log("connect+init OK")
    except Exception as e:
        log(f"connect FAIL: {e}")
        return 1

    # ---------- 1. LIGHT MODE (V1 buffered pass execution) ----------
    log("")
    log("--- light mode (red-dot outline, per-pass buffered execute) ---")
    try:
        ctrl.light_mode()
        ctrl.light(0x7000, 0x7000)
        ctrl.light(0x9000, 0x7000)
        ctrl.light(0x9000, 0x9000)
        ctrl.light(0x7000, 0x9000)
        ctrl.light(0x7000, 0x7000)
        ctrl.light_off()
        ctrl.write_port()
        ctrl.v1_execute_light_list()      # V1: execute whole pass + wait
        st = ctrl.status()
        ok = st == 0x0220
        log(f"  light pass execute -> state={hex(st) if st else None} "
            f"{'OK' if ok else 'FAIL'}")
        ctrl.abort()                      # V1 abort (light job stop path)
        st = ctrl.status()
        log(f"  abort after light -> state={hex(st) if st else None} "
            f"{'OK' if st == 0x0220 else 'FAIL'}")
    except Exception as e:
        log(f"  light mode FAIL: {e}")

    # ---------- 2. REALTIME COMMANDS (non-axis) ----------
    log("")
    log("--- realtime commands (non-axis) ---")
    tests = [
        (0x0002, "DisableLaser"), (0x000A, "GetListStatus"),
        (0x000E, "LaserSignalOff"), (0x000F, "LaserSignalOn"),
        (0x0010, "WriteCorLine"), (0x0013, "RestartList"),
        (0x0018, "SetMaxPolyDelay"), (0x0020, "StopList"),
        (0x0023, "WriteAnalogPort2"), (0x0024, "WriteAnalogPortX"),
        (0x0025, "ReadPort"), (0x002B, "GetFlyWaitCount"),
        (0x002D, "GetMarkCount"), (0x002E, "SetFpkParam2"),
        (0x0039, "DisableZ"), (0x003B, "SetZData"),
        (0x003C, "SetSPISimmerCurrent"), (0x0040, "Reset"),
    ]
    for code, name in tests:
        try:
            r = ctrl._command(code)
            st = ctrl.status()
            ok = st == 0x0220
            log(f"  {code:04X} {name:<22} {'OK' if ok else 'FAIL'} "
                f"resp={r} state={hex(st) if st else None}")
        except Exception as e:
            log(f"  {code:04X} {name:<22} FAIL {e}")

    # ---------- 3. LIST RECORDS (via shim flow, auto-recovery) ----------
    log("")
    log("--- list records (each in a full job) ---")
    records = [
        (0x8003, "listLaserOnPoint(dwell)", (0x000A,)),
        (0x8023, "listChangeMarkCount", (0x0002,)),
        (0x8021, "listFiberOpenMO", (0x0000,)),
        (0x8026, "listFiberYLPMPulseWidth", (0x0064,)),
        (0x8029, "listSetDaZWord", (0x0000,)),
        (0x801D, "listFlyDelay", (0x0000, 0x0000)),
    ]
    for code, name, args in records:
        try:
            ctrl.program_mode()
            # settings (speed records, power ZERO)
            ctrl.list_jump_speed(0x0D1B)
            ctrl.list_mark_speed(0x0320)
            ctrl.list_mark_current(0x0000)   # ZERO power - safe
            ctrl.list_qswitch_period(0x03E8)
            # the record under test
            pkt = struct.pack('<6H', code, *args, *(0,) * (6 - 1 - len(args)))
            ctrl._list_write.__wrapped__ if False else None
            ctrl._active_list[ctrl._active_index:ctrl._active_index + 12] = pkt
            ctrl._active_index += 12
            # small square
            ctrl.goto(0x7500, 0x7500)
            ctrl.mark(0x8B00, 0x7500)
            ctrl.mark(0x8B00, 0x8B00)
            ctrl.mark(0x7500, 0x8B00)
            ctrl.mark(0x7500, 0x7500)
            ctrl.rapid_mode()
            st = ctrl.status()
            ok = st == 0x0220
            log(f"  {code:04X} {name:<30} {'OK' if ok else 'FAIL'} "
                f"state={hex(st) if st else None}")
        except Exception as e:
            log(f"  {code:04X} {name:<30} FAIL {e}")

    # ---------- 3b. UNVERIFIED ROUND 2 (probe everything else) ----------
    log("")
    log("--- realtime round 2 (previously unverified) ---")
    for code, name, args in [
        (0x001F, "StopExecute", ()),
        (0x002F, "FiberPulseWidth", ()),
        (0x0030, "FiberGetConfigExtend", ()),
        (0x0031, "InputPort", (0,)),
        (0x0036, "GetUserData", ()),
        (0x0038, "GetFlySpeed", ()),
    ]:
        try:
            r = ctrl._command(code, *args)
            st = ctrl.status()
            ok = st == 0x0220
            log(f"  {code:04X} {name:<24} {'OK' if ok else 'FAIL'} "
                f"resp={r} state={hex(st) if st else None}")
        except Exception as e:
            log(f"  {code:04X} {name:<24} FAIL {e}")

    log("")
    log("--- list records round 2 (previously unverified) ---")
    for code, name, args in [
        (0x8007, "listLaserOnDelay", (0x012C,)),
        (0x8008, "listLaserOffDelay", (0x0064,)),
        (0x800D, "listJumpDelay", (0x0064,)),
        (0x800F, "listPolygonDelay", (0x000A,)),
        (0x8013, "listMarkFreq2", (0x0001,)),
        (0x800B, "listMarkPowerRatio", (0x0001,)),
        (0x801A, "listFlyEnable", (0x0000,)),
        (0x801C, "listDirectLaserSwitch", (0x0000,)),
        (0x801E, "listSetCo2FPK", (0x0043, 0x0043)),
        (0x801F, "listFlyWaitInput", (0x0000, 0x0000)),
        (0x8022, "listWaitForInput", (0x0000, 0x0000)),
        (0x8024, "listSetWeldPowerWave", (0x0000,)),
        (0x8025, "listEnableWeldPowerWave", (0x0000,)),
        (0x8028, "listFlyEncoderCount", (0x0000,)),
        (0x8050, "listJptSetParam", (0x0000, 0x0000)),
    ]:
        try:
            ctrl.program_mode()
            ctrl.list_jump_speed(0x0D1B)
            ctrl.list_mark_speed(0x0320)
            ctrl.list_mark_current(0x0000)   # ZERO power - safe
            ctrl.list_qswitch_period(0x03E8)
            pkt = struct.pack('<6H', code, *args, *(0,) * (6 - 1 - len(args)))
            ctrl._active_list[ctrl._active_index:ctrl._active_index + 12] = pkt
            ctrl._active_index += 12
            ctrl.goto(0x7500, 0x7500)
            ctrl.mark(0x8B00, 0x7500)
            ctrl.mark(0x8B00, 0x8B00)
            ctrl.mark(0x7500, 0x8B00)
            ctrl.mark(0x7500, 0x7500)
            if code in (0x801F, 0x8022):
                # wait-for-input records: the board waits for an input
                # signal that never comes - execute WITHOUT waiting
                ctrl.list_end_of_list()
                ctrl._list_end()
                ctrl.execute_list()
                ctrl._command(0x0016, 1)
                time.sleep(0.5)
            else:
                ctrl.rapid_mode()
            st = ctrl.status()
            ok = st == 0x0220
            if st in (0x0234, 0x0226):
                ctrl._command(0x001F)
                ctrl.reset_list()
                ctrl._command(0x0021, 0)
                ctrl._command(0x001D, 2000, 20, 1)
                ctrl._command(0x0033, 0)
                time.sleep(0.3)
                st = ctrl.status()
                ok = st == 0x0220
                log(f"  {code:04X} {name:<30} ACCEPTED (needs input) "
                    f"recovered={hex(st) if st else None}")
            else:
                log(f"  {code:04X} {name:<30} {'OK' if ok else 'FAIL'} "
                    f"state={hex(st) if st else None}")
        except Exception as e:
            log(f"  {code:04X} {name:<30} FAIL {e}")

    # ---------- 4. AXIS COMMANDS (last - they set AXIS state) ----------
    log("")
    log("--- axis commands (set AXIS flag - expected state change) ---")
    for code, name in [(0x0026, "SetAxisMotionParam"), (0x0027, "SetAxisOriginParam"),
                       (0x0028, "AxisGoOrigin"), (0x0029, "MoveAxisTo"),
                       (0x002A, "GetAxisPos")]:
        try:
            r = ctrl._command(code)
            st = ctrl.status()
            log(f"  {code:04X} {name:<22} resp={r} state={hex(st) if st else None}")
        except Exception as e:
            log(f"  {code:04X} {name:<22} FAIL {e}")

    # recovery to normal
    try:
        ctrl._command(0x0009); ctrl._command(0x0034); ctrl.wait_ready()
        ctrl.reset_list(); ctrl._command(0x000C)
        st = ctrl.status()
        log(f"  post-axis recovery -> state={hex(st) if st else None}")
    except Exception as e:
        log(f"  recovery FAIL: {e}")

    ctrl.disconnect()
    with open(LOG, "w") as f:
        f.write("\n".join(lines) + "\n")
    log(f"\n(log written to {LOG})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
