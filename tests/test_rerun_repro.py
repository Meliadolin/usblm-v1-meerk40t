#!/usr/bin/env python3
"""Reproduce: does job B re-run job A's records?
Job A = 140 chunks of marks, Job B = 42 chunks.
If B re-runs A, B's run takes ~4x longer."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def run_job(ctrl, n_chunks, name, mark_power=0x00C8):
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    ctrl.list_qswitch_period(0x03E8)
    total = n_chunks * 256
    for i in range(total):
        ctrl._list_write(0x8012, mark_power, 0, 0, 0, 0)
        ctrl._list_write(0x8005, 0x7500 + (i % 40), 0x7500 + ((i // 40) % 40),
                         0x8000, 1)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    print(f"{name:<34} chunks={n_chunks:4d} -> {dur:6.2f}s "
          f"state={hex(st) if st else None}", flush=True)
    return dur, st


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    # baseline: small job alone
    d0, s0 = run_job(ctrl, 42, "baseline 42 chunks")
    # big job (like the text)
    d1, s1 = run_job(ctrl, 140, "job A 140 chunks (text-like)")
    # small job after (like the circle) - does it re-run A?
    d2, s2 = run_job(ctrl, 42, "job B 42 chunks AFTER A")
    if s1 != 0x0220:
        print(f"!! job A ended at {hex(s1)} - abnormal")
    if d2 > d0 * 2:
        print(f"!! JOB B RE-RAN JOB A: {d2:.2f}s vs baseline {d0:.2f}s")
    else:
        print(f"OK: job B ran clean ({d2:.2f}s vs baseline {d0:.2f}s)")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
