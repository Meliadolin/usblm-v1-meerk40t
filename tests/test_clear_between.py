#!/usr/bin/env python3
"""Does reset_list actually clear the board's list between jobs?
Job A: 3 chunks of jumps. Job B: 1 chunk. If B re-ran A's leftover
records, B would take ~tA+tB. We check the RUNTIME ratio instead of a
final position, because rapid_mode homes the galvo to center at run
end (0x000D(0x8000,0x8000) - EZCAD behavior, see PROTOCOL.md), so the
position after ANY job is center, never the last mark.

V1 0x000C GetPositionXY response layout (verified on hardware):
  w[3] = galvo X position (0x0000..0xFFFF, center 0x8000)
  no Y is returned. (balormk's [w1=x, w2=y] layout does not apply.)"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService


def pos(ctrl):
    """Read the galvo X position: V1 puts it in w[3] of the 0x000C
    response (raw send form). Returns None if the board did not answer."""
    r = ctrl.get_position_xy()
    if r and len(r) >= 4 and r[0] in (0x000C, 0x0002):
        return r[3]
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
    x = pos(ctrl)
    print(f"{name:<30} -> {dur:5.2f}s state={hex(st) if st else None} "
          f"x={hex(x) if x is not None else None}", flush=True)
    return dur, st, x


def main():
    ctrl = V1Controller(FakeService())
    ctrl.connect_if_needed()

    # job A: 3 chunks of jumps (700 points)
    ptsA = [(0x7600 + i % 30, 0x7600 + (i // 30) % 30) for i in range(700)]
    # job B: 1 chunk (100 points)
    ptsB = [(0x8E00 + i % 10, 0x8E00 + (i // 10) % 10) for i in range(100)]

    tA, stA, xA = run_job(ctrl, ptsA, "job A (3 chunks)")
    tB, stB, xB = run_job(ctrl, ptsB, "job B (1 chunk)")

    clean = (stB in (0x0220, 0x0260) and tB < tA / 2.0)
    if clean:
        print("CLEAN: job B ran its own list only "
              f"(tB={tB:.2f}s < tA/2={tA/2:.2f}s)")
    else:
        print("CONTAMINATED: job B took too long - leftover records "
              f"re-ran (tA={tA:.2f}s, tB={tB:.2f}s)")

    if xB is not None and abs(xB - 0x8000) <= 100:
        print(f"OK: galvo homed to center after job B (x={hex(xB)})")
    else:
        print(f"WARNING: expected center (0x8000) after job B, "
              f"got x={hex(xB) if xB is not None else None}")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
