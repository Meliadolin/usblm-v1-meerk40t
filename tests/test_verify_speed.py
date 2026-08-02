#!/usr/bin/env python3
"""Verify: marks vs power-record chunk ingestion speed."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def build(ctrl, n_chunks, with_power):
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    ctrl.list_qswitch_period(0x03E8)
    total = n_chunks * 256
    t0 = time.time()
    for i in range(total):
        if with_power:
            ctrl._list_write(0x8012, 0x00C8, 0, 0, 0, 0)
            ctrl._list_write(0x8005, 0x7500 + (i % 40), 0x7500 + ((i // 40) % 40),
                             0x8000, 1)
        else:
            ctrl._list_write(0x8005, 0x7500 + (i % 40), 0x7500 + ((i // 40) % 40),
                             0x8000, 1)
    t1 = time.time()
    ctrl.rapid_mode()
    t2 = time.time()
    print(f"{'power' if with_power else 'marks':6s} {n_chunks:3d} chunks: "
          f"build={(t1-t0):.1f}s ({(t1-t0)/n_chunks*1000:.0f} ms/chunk) "
          f"run={(t2-t1):.1f}s", flush=True)


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()
    build(ctrl, 60, False)
    build(ctrl, 60, True)
    ctrl.disconnect()


if __name__ == "__main__":
    main()
