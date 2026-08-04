#!/usr/bin/env python3
"""After the fix: pause the board, then run a normal job through
rapid_mode - it must clear the pause and run the NEW list clean."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService


def build(ctrl, n, speed):
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(speed)
    ctrl.list_mark_current(0x0000)
    for i in range(n):
        ctrl._list_write(0x8005, 0x7600 + (i % 40) * 10,
                         0x7600 + ((i // 40) % 40) * 10, 0x8000, 10)


def main():
    ctrl = V1Controller(FakeService())
    ctrl.connect_if_needed()

    # list A: long, launch, pause mid-run
    build(ctrl, 2000, 0x0064)
    ctrl.list_end_of_list()
    ctrl._list_end()
    ctrl.execute_list()
    ctrl._command(0x0016, 1)
    time.sleep(0.5)
    ctrl.stop_list()
    time.sleep(0.4)
    st = ctrl.status()
    print(f"A paused, state={hex(st) if st else None}", flush=True)

    # short job B via the REAL flow (rapid_mode -> _clear_pause)
    build(ctrl, 200, 0x0320)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    print(f"job B via rapid_mode -> {dur:.2f}s state={hex(st) if st else None}", flush=True)
    if dur > 4:
        print("!! STALE RUN STILL PRESENT")
    else:
        print("OK: pause cleared, B ran its own list")
    ctrl.abort()
    ctrl.disconnect()


if __name__ == "__main__":
    main()
