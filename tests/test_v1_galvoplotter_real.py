#!/usr/bin/env python3
"""REAL HARDWARE test of the V1 galvoplotter profile.
Marks a small square near center at low power using galvoplotter's
own command layer (the library MeerK40t is built on)."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import v1_galvoplotter
from v1_galvoplotter import V1GalvoController


def main():
    ctrl = V1GalvoController(
        x=0x8000, y=0x8000,
        mark_speed=200.0,
        travel_speed=2000.0,
        power=15.0,        # low power for the test
        frequency=20.0,
        delay_open_mo=8.0,
        usb_log=lambda s: print(f"  [log] {s}"),
    )
    try:
        print("=== connect ===")
        ctrl.connect_if_needed()

        print("=== marking square (low power 15%) ===")
        with ctrl.marking() as c:
            c.goto(0x6000, 0x6000)
            c.mark(0x6000, 0xA000)
            c.mark(0xA000, 0xA000)
            c.mark(0xA000, 0x6000)
            c.mark(0x6000, 0x6000)

        print("=== waiting for idle ===")
        ctrl.wait_for_machine_idle()
        print("JOB DONE - square marked, galvo idle")
    finally:
        ctrl.disconnect()


if __name__ == "__main__":
    main()
