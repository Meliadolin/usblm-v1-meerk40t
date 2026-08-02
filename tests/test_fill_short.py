#!/usr/bin/env python3
"""SHORT fill test - 5 lines only, ~15s. Laser fires on mark records."""
import os
import struct
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from v1_controller import V1Controller

ctrl = V1Controller()
try:
    ctrl.connect()
    ctrl.init()

    # build a SHORT fill chunk manually: 5 lines, step 0x800 (2048)
    x0, y0, x1, y1 = 0x6000, 0x6000, 0xA000, 0xA000
    step = 0x800
    records = []
    records.append(ctrl._seg(0x8051, 0, 0, 0, 0))       # listReadyMark
    records.append(ctrl._seg(0x8004, 0x0320, 0, 0, 0))  # open-MO delay
    records.append(ctrl._seg(0x8011, 0x0001, 0, 0, 0))  # listWritePort
    records.append(ctrl._seg(0x8004, 0x01F4, 0, 0, 0))  # mark delay
    records.append(ctrl._seg(0x801B, 0x03E8, 0, 0, 0))  # Q-switch
    records.append(ctrl._seg(0x8012, 0x0FFF, 0, 0, 0))  # POWER max
    records.append(ctrl._seg(0x8006, 0x0D1B, 0, 0, 0))  # jump speed
    records.append(ctrl._seg(0x800C, 0x01A3, 0, 0, 0))  # mark speed 419
    records.append(ctrl._seg(0x8007, 0x012C, 0, 0, 0))
    records.append(ctrl._seg(0x8008, 0x0064, 0, 0, 0))
    records.append(ctrl._seg(0x800F, 0x000A, 0, 0, 0))
    records.append(ctrl._seg(0x800D, 0x0199, 0, 0, 0))
    px, py = 0x8000, 0x8000
    y = y0
    row = 0
    while y <= y1:
        if row % 2 == 0:
            sx, ex = x0, x1
        else:
            sx, ex = x1, x0
        d = ctrl._dist(px, py, sx, y)
        records.append(ctrl._seg(0x8001, sx, y, 0, d))
        px, py = sx, y
        d = ctrl._dist(px, py, ex, y)
        records.append(ctrl._seg(0x8005, ex, y, 0x8000, d))
        px, py = ex, y
        y += step
        row += 1
    chunk = b''.join(records)
    n_pad = (3072 - len(chunk)) // 12
    chunk += ctrl._seg(0x8002, 0, 0, 0, 0) * n_pad

    print(f"chunk: {len(chunk)}B, {len(records)} real records + {n_pad} terminators")
    for i in range(0, min(len(chunk), 96), 12):
        w = struct.unpack_from('<6H', chunk, i)
        print(f"  {w}")

    print("\n--- firing SHORT fill (5 lines, laser ON) ---")
    ctrl._run_chunk(chunk, duration=15.0, stop=True, laser=True)
    print("short fill DONE - did the laser fire on the lines?")
finally:
    ctrl.disconnect()
