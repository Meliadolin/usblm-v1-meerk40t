#!/usr/bin/env python3
"""Does reset_list actually clear the board's list between jobs?
Job A: marks ending at position PA. Job B: marks ending at PB.
If B re-runs A's leftover records, the final position != PB."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_meerk40t
from v1_meerk40t import V1MKController
from test_v1_meerk40t_real import FakeService


def pos(ctrl):
    """Read the galvo position via 0x000C GetPositionXY."""
    r = ctrl.get_position_xy()
    if r and len(r) >= 4:
        return r[1], r[2]
    return None


def run_job(ctrl, points, name):
    ctrl.program_mode()
    ctrl.list_jump_speed(0x0D1B)
    ctrl.list_mark_speed(0x0320)
    ctrl.list_mark_current(0x0000)
    for x, y in points:
        ctrl._list_write(0x8001, x, y, 0, 100, 0)
    ctrl._list_write(0x8005, points[-1][0], points[-1][1], 0x8000, 100, 0)
    t0 = time.time()
    ctrl.rapid_mode()
    dur = time.time() - t0
    st = ctrl.status()
    p = pos(ctrl)
    print(f"{name:<30} -> {dur:5.2f}s state={hex(st) if st else None} "
          f"pos={p}", flush=True)
    return p


def main():
    ctrl = V1MKController(FakeService())
    ctrl.connect_if_needed()

    # job A: 3 chunks of jumps ending at (0x7500, 0x7500)
    ptsA = [(0x7600 + i % 30, 0x7600 + (i // 30) % 30) for i in range(700)]
    # job B: 1 chunk ending at (0x8F00, 0x8F00)
    ptsB = [(0x8E00 + i % 10, 0x8E00 + (i // 10) % 10) for i in range(100)]

    pA = run_job(ctrl, ptsA, "job A (3 chunks, ends 7500)")
    pB = run_job(ctrl, ptsB, "job B (1 chunk, ends 8F00)")
    if pB and abs(pB[0] - 0x8F00) < 300 and abs(pB[1] - 0x8F00) < 300:
        print("CLEAN: job B ended at its own last mark")
    else:
        print("CONTAMINATED: job B did NOT end at its own last mark")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
