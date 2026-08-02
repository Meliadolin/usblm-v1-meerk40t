#!/usr/bin/env python3
"""Small raster probe: find the wedge record pattern.
Tests small lists (a few chunks each) so runs are fast."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def run(ctrl, recs, name):
    """recs: list of (code, args...) tuples. Build via _list_write, execute."""
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    ctrl.list_qswitch_period(0x03E8)
    for rec in recs:
        ctrl._list_write(*rec)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    ok = st in (0x0220, 0x0260)
    print(f"{name:<38} -> {dur:5.1f}s {hex(st) if st else None} "
          f"{'OK' if ok else 'WEDGED'}", flush=True)
    if not ok:
        ctrl._command(0x001F)
        ctrl.reset_list()
        ctrl._command(0x0021, 0)
        ctrl._command(0x001D, 2000, 20, 1)
        ctrl._command(0x0033, 0)
        time.sleep(0.3)
        print(f"   recovered -> {hex(ctrl.status()) if ctrl.status() else None}")


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    # pattern tests: ~600 records each (2-3 chunks)
    marks_d1 = [(0x8005, 0x7500 + i % 40, 0x7500 + (i // 40) % 40, 0x8000, 1)
                for i in range(600)]
    marks_d42 = [(0x8005, 0x7500 + (i % 40) * 42, 0x7500 + (i // 40) * 42,
                  0x8000, 42) for i in range(600)]
    px_power = []
    for i in range(600):
        px_power.append((0x8012, 0x00C8 + (i % 50) * 5, 0, 0, 0))
        px_power.append((0x8005, 0x7500 + i % 40, 0x7500 + (i // 40) % 40,
                         0x8000, 1))
    px_power_d42 = []
    for i in range(600):
        px_power_d42.append((0x8012, 0x00C8 + (i % 50) * 5, 0, 0, 0))
        px_power_d42.append((0x8005, 0x7500 + i % 40, 0x7500 + (i // 40) % 40,
                             0x8000, 42))

    run(ctrl, marks_d1, "marks dist=1")
    run(ctrl, marks_d42, "marks dist=42")
    run(ctrl, px_power, "power+mark dist=1")
    run(ctrl, px_power_d42, "power+mark dist=42")
    run(ctrl, marks_d1, "marks dist=1 again")

    ctrl.disconnect()


if __name__ == "__main__":
    main()
