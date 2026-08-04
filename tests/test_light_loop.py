#!/usr/bin/env python3
"""Reproduce the live light-trace loop WITHOUT the GUI: 5 timed passes."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService


def main():
    ctrl = V1Controller(FakeService())
    ctrl.connect_if_needed()
    ctrl.light_mode()

    # a small square path, like the light job's interpolated points
    pts = []
    for i in range(0, 55, 1):
        pts.append((0x7500 + i * 10, 0x7500))
    for i in range(0, 55, 1):
        pts.append((0x8500, 0x7500 + i * 10))
    for i in range(0, 55, 1):
        pts.append((0x8500 - i * 10, 0x8500))
    for i in range(0, 55, 1):
        pts.append((0x7500, 0x8500 - i * 10))

    for pass_no in range(5):
        t0 = time.time()
        ctrl.light(pts[0][0], pts[0][1])
        for x, y in pts[1:]:
            ctrl.light(x, y)
        ctrl.dark(pts[0][0], pts[0][1])
        t_build = time.time() - t0
        ctrl.light_off()
        ctrl.write_port()
        ctrl.v1_execute_light_list()
        t_total = time.time() - t0
        st = ctrl.status()
        print(f"pass {pass_no}: build={t_build:.3f}s total={t_total:.3f}s "
              f"state={hex(st) if st else None}", flush=True)

    ctrl.abort()
    st = ctrl.status()
    print(f"abort -> state={hex(st) if st else None}")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
