#!/usr/bin/env python3
"""Measure the V1 board's list capacity: how many 3072B chunks fit?"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def run_chunks(ctrl, n_chunks, name):
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    # n_chunks worth of jump records
    total = n_chunks * 256
    for i in range(total):
        ctrl.goto(0x7500 + (i % 40) * 10, 0x7500 + ((i // 40) % 40) * 10)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    ok = st in (0x0220, 0x0260)
    print(f"{name:<28} chunks={n_chunks:4d} -> {dur:5.1f}s state={hex(st) if st else None} "
          f"{'OK' if ok else 'WEDGED'}", flush=True)
    if not ok:
        ctrl._command(0x001F)
        ctrl.reset_list()
        ctrl._command(0x0021, 0)
        ctrl._command(0x001D, 2000, 20, 1)
        ctrl._command(0x0033, 0)
        time.sleep(0.3)
        st = ctrl.status()
        print(f"   recovered -> {hex(st) if st else None}", flush=True)
    return ok


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()
    run_chunks(ctrl, 8, "baseline")
    run_chunks(ctrl, 16, "16 chunks (48KB)")
    run_chunks(ctrl, 32, "32 chunks (96KB)")
    run_chunks(ctrl, 64, "64 chunks (192KB)")
    run_chunks(ctrl, 256, "256 chunks (768KB)"); run_chunks(ctrl, 360, "360 chunks (1.08MB)")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
