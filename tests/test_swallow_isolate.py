#!/usr/bin/env python3
"""Isolate the swallowed-job: which step breaks the next job?"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def build_and_run(ctrl, name):
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
    verdict = "RAN" if dur > 0.5 else "SWALLOWED"
    print(f"{name:<38} -> {dur:5.2f}s {hex(st) if st else None} {verdict}",
          flush=True)
    return dur


def light_pass(ctrl):
    ctrl.light_mode()
    for i in range(50):
        ctrl.light(0x7500 + (i % 20) * 10, 0x7500 + (i // 20) * 200)
    ctrl.light_off()
    ctrl.write_port()
    ctrl.v1_execute_light_list()


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    build_and_run(ctrl, "baseline (no light)")
    light_pass(ctrl)
    build_and_run(ctrl, "after light pass (no abort)")
    ctrl.abort()
    build_and_run(ctrl, "after light + abort")
    ctrl.abort()
    ctrl.restart_list()
    build_and_run(ctrl, "after abort + restart_list")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
