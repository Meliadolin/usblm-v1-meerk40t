#!/usr/bin/env python3
"""Recovery probe: confirm the CPUCS reboot clears a wedged board."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService


def main():
    ctrl = V1Controller(FakeService())
    ctrl.connect_if_needed()
    st = ctrl.status()
    print(f"state before: {hex(st) if st else None}")

    if st not in (0x0220, 0x0260):
        print("wedged - CPUCS reboot...")
        ctrl._cpu_reset()
        time.sleep(0.8)
        try:
            ctrl.init_laser()
        except Exception as e:
            print(f"re-init FAILED: {e}")
        st = ctrl.status()
        print(f"state after reboot: {hex(st) if st else None}")

    # normal job to prove the board is fully functional
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    ctrl.goto(0x7000, 0x7000)
    ctrl.mark(0x9000, 0x7000)
    ctrl.mark(0x9000, 0x9000)
    ctrl.mark(0x7000, 0x9000)
    ctrl.mark(0x7000, 0x7000)
    ctrl.rapid_mode()
    st = ctrl.status()
    ok = st == 0x0220
    print(f"square job -> state={hex(st) if st else None} {'OK' if ok else 'FAIL'}")
    ctrl.disconnect()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
