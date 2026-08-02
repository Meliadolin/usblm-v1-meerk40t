#!/usr/bin/env python3
"""Large raster job (100k pixels) - the size that used to be murdered."""
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
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    ctrl.list_qswitch_period(0x03E8)
    n = 100000
    t0 = time.time()
    for i in range(n):
        ctrl._list_write(0x8012, 0x00C8 + (i % 50) * 5, 0, 0, 0, 0)
        ctrl._list_write(0x8005, 0x7500 + (i % 40), 0x7500 + ((i // 40) % 40),
                         0x8000, 1)
    print(f"built {n*2} records in {time.time()-t0:.1f}s", flush=True)
    t0 = time.time()
    ctrl.rapid_mode()
    print(f"rapid_mode in {time.time()-t0:.1f}s", flush=True)
    st = ctrl.status()
    print(f"state: {hex(st) if st else None} - "
          f"{'OK' if st == 0x0220 else 'FAIL'}", flush=True)
    ctrl.disconnect()


if __name__ == "__main__":
    main()
