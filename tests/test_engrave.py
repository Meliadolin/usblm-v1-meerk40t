#!/usr/bin/env python3
"""ENGRAVING TEST - LASER WILL FIRE. 10s continuous square, then outline mark, then fill."""
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from v1_controller import V1Controller

ctrl = V1Controller()
try:
    ctrl.connect()
    ctrl.init()

    print("\n" + "!" * 60)
    print("!!! LASER WILL FIRE IN THE NEXT STEPS - EYES AND SKIN PROTECTION !!!")
    print("!" * 60)

    print("\n--- 1. continuous square outline (10s, no laser) ---")
    ctrl.outline([
        (0x6000, 0x6000),
        (0xA000, 0x6000),
        (0xA000, 0xA000),
        (0x6000, 0xA000),
        (0x6000, 0x6000),
    ], duration=10.0, pad_to=0)
    print("  continuous outline DONE")

    time.sleep(0.5)

    print("\n--- 2. ENGRAVE: square outline (LASER ON, 1 pass, SLOW) ---")
    ctrl.mark([
        (0x6000, 0x6000),
        (0xA000, 0x6000),
        (0xA000, 0xA000),
        (0x6000, 0xA000),
        (0x6000, 0x6000),
    ], mark_speed=0x0010, power=0x0FFF)
    print("  outline engrave DONE")

    time.sleep(0.5)

    print("\n--- 3. ENGRAVE: filled square (LASER ON, hatch lines, SLOW) ---")
    ctrl.fill(0x6000, 0x6000, 0xA000, 0xA000,
              step=0x200, mark_speed=0x0040, power=0x0FFF, stop=True)
    print("  fill engrave DONE")

    print("\nALL DONE - check the result!")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"\nFAILED: {e}")
finally:
    ctrl.disconnect()
