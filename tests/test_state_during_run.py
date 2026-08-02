#!/usr/bin/env python3
"""Watch the board state DURING a slow raster-style run.
If the state shows 0x234 (ready+busy+0x10) mid-run, then 0x234 IS a
legitimate running state for raster lists and the recovery ladder must
never kill it."""
import os
import struct
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService

STATES = []
STOP = False


def poller(ctrl):
    while not STOP:
        st = ctrl.status()
        if st is not None:
            STATES.append(st)
        time.sleep(0.15)


def main():
    global STOP
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)      # run takes many seconds
    ctrl.list_qswitch_period(0x03E8)
    n = 3000
    for i in range(n):
        ctrl._list_write(0x8012, 0x00C8, 0, 0, 0, 0)
        ctrl._list_write(0x8005, 0x7500 + i % 40, 0x7500 + (i // 40) % 40,
                         0x8000, 1)

    t = threading.Thread(target=poller, args=(ctrl,), daemon=True)
    t.start()
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    STOP = True
    t.join(timeout=1)
    st = ctrl.status()
    uniq = sorted(set(STATES))
    print(f"run took {dur:.1f}s, end state={hex(st) if st else None}")
    print(f"states seen DURING run: {[hex(s) for s in uniq]}")
    ok = st in (0x0220, 0x0260)
    print(f"{'OK - run completed' if ok else 'WEDGED'}")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
