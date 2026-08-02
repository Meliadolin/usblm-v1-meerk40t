#!/usr/bin/env python3
"""Simulate the user flow: light pass running -> user starts a real job.
Does the real job run, or get swallowed?"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    # 1. start a light pass (simulates the live trace being active)
    ctrl.light_mode()
    for i in range(50):
        ctrl.light(0x7500 + (i % 20) * 10, 0x7500 + (i // 20) * 200)
    ctrl.light_off()
    ctrl.write_port()
    ctrl.v1_execute_light_list()
    st = ctrl.status()
    print(f"light pass done -> {hex(st) if st else None}", flush=True)

    # 2. the light job gets aborted (post_job), like the spooler does
    ctrl.abort()
    st = ctrl.status()
    print(f"after abort -> {hex(st) if st else None}", flush=True)

    # 3. real job starts: program_mode + build + rapid_mode
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    for i in range(200):
        ctrl._list_write(0x8005, 0x7600 + (i % 20) * 10, 0x7600 + (i // 20) * 10,
                         0x8000, 10)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    print(f"real job -> {dur:.2f}s state={hex(st) if st else None} "
          f"{'RAN' if dur > 0.5 else 'SWALLOWED'}", flush=True)
    ctrl.disconnect()


if __name__ == "__main__":
    main()
