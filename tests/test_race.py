#!/usr/bin/env python3
"""The race: light pass mid-flight while a real job starts.
With the fix, the job must wait for the pass, then run."""
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

    # slow light pass: 3000 points, execute WITHOUT waiting
    ctrl.light_mode()
    for i in range(3000):
        ctrl.light(0x7500 + (i % 60) * 10, 0x7500 + ((i // 60) % 50) * 10)
    ctrl.light_off()
    ctrl.write_port()
    ctrl.list_end_of_list()
    ctrl._list_end()
    ctrl.execute_list()
    ctrl._command(0x0016, 1)
    st = ctrl.status()
    print(f"light pass launched, state={hex(st) if st else None} "
          f"(busy={bool(st & 0x04) if st else '?'})", flush=True)

    # IMMEDIATELY start a real job - must wait for the pass, then run
    t0 = time.time()
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    for i in range(200):
        ctrl._list_write(0x8005, 0x7600 + (i % 20) * 10, 0x7600 + (i // 20) * 10,
                         0x8000, 10)
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    print(f"real job total: {dur:.2f}s state={hex(st) if st else None}", flush=True)
    # the job should have run (200 marks ~0.4s + the pass wait)
    ok = st == 0x0220 and dur > 0.8
    print(f"{'OK - waited for the pass, then ran' if ok else 'FAIL'}", flush=True)
    ctrl.disconnect()


if __name__ == "__main__":
    main()
