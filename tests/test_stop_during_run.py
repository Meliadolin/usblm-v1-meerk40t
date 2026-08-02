#!/usr/bin/env python3
"""During a run: does StopList pause (0x238) vs StopExecute (0x220)?
And: can a paused board run a new list?"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def launch_run(ctrl):
    """Start a slow list running (marks), don't wait."""
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0064)      # slower marks so the run lasts
    ctrl.list_mark_current(0x0000)
    for i in range(2000):
        ctrl._list_write(0x8005, 0x7600 + (i % 40) * 10, 0x7600 + ((i // 40) % 40) * 10,
                         0x8000, 10)
    ctrl.list_end_of_list()
    ctrl._list_end()
    ctrl.execute_list()
    ctrl._command(0x0016, 1)
    time.sleep(0.4)
    st = ctrl.status()
    print(f"run launched, state={hex(st) if st else None}", flush=True)
    return st


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    # A: stop_list during a run
    st = launch_run(ctrl)
    ctrl.stop_list()
    time.sleep(0.5)
    st = ctrl.status()
    print(f"stop_list during run -> {hex(st) if st else None} "
          f"(paused={bool(st & 0x08) if st else '?'})", flush=True)
    # can the board run a new list now?
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    for i in range(100):
        ctrl._list_write(0x8005, 0x7800 + (i % 20) * 10, 0x7800 + (i // 20) * 10,
                         0x8000, 10)
    ctrl.list_end_of_list()
    ctrl._list_end()
    ctrl.execute_list()
    ctrl._command(0x0016, 1)
    t0 = time.time()
    while ctrl.is_busy() and time.time() - t0 < 5:
        time.sleep(0.05)
    st = ctrl.status()
    print(f"new list after stop_list -> state={hex(st) if st else None}", flush=True)
    ctrl.restart_list()
    time.sleep(0.3)
    st = ctrl.status()
    print(f"after restart_list -> {hex(st) if st else None}", flush=True)

    # B: stop_execute during a run
    st = launch_run(ctrl)
    ctrl._command(0x001F)
    time.sleep(0.5)
    st = ctrl.status()
    print(f"stop_execute during run -> {hex(st) if st else None}", flush=True)
    ctrl.abort()
    st = ctrl.status()
    print(f"after abort -> {hex(st) if st else None}", flush=True)
    ctrl.disconnect()


if __name__ == "__main__":
    main()
