#!/usr/bin/env python3
"""3-direction fill (H + V + D) as ONE buffered job via ctrl.mark_job().
The flagship test - exercises the complete verified protocol."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from v1_controller import V1Controller

X0, Y0, X1, Y1 = 0x6000, 0x6000, 0xA000, 0xA000
N = 64
STEP = (X1 - X0) // N


def horizontal():
    return [(X0, Y0 + k*STEP, X1, Y0 + k*STEP) if k % 2 == 0
            else (X1, Y0 + k*STEP, X0, Y0 + k*STEP) for k in range(N)]


def vertical():
    return [(X0 + k*STEP, Y0, X0 + k*STEP, Y1) if k % 2 == 0
            else (X0 + k*STEP, Y1, X0 + k*STEP, Y0) for k in range(N)]


def diagonal():
    """45-degree lines y = x + s covering the FULL square.
    s spans -width..+width (corner to corner), step = 2*width/N."""
    segs = []
    s_range = 2 * (X1 - X0)
    s_step = s_range // N
    for k in range(N):
        s = -s_range // 2 + s_step // 2 + k * s_step   # centered
        pts = []
        y = X0 + s
        if Y0 <= y <= Y1:
            pts.append((X0, y))
        y = X1 + s
        if Y0 <= y <= Y1:
            pts.append((X1, y))
        x = Y0 - s
        if X0 <= x <= X1:
            pts.append((x, Y0))
        x = Y1 - s
        if X0 <= x <= X1:
            pts.append((x, Y1))
        if len(pts) == 2:
            pts.sort()
            (ax, ay), (bx, by) = pts
            segs.append((ax, ay, bx, by) if k % 2 == 0 else (bx, by, ax, ay))
    return segs


def main():
    ctrl = V1Controller()
    try:
        ctrl.connect()
        ctrl.init()

        all_segs = horizontal() + vertical() + diagonal()
        print(f"3-direction fill: {len(all_segs)} segments "
              f"({N} lines per direction), one job")
        ctrl.mark_job(all_segs, mark_speed=0x0320, power=0x0FFF,
                      freq=0x03E8, stop=True)
        print("JOB DONE - H + V + D engraved, galvo at center")
    finally:
        ctrl.disconnect()


if __name__ == "__main__":
    main()
