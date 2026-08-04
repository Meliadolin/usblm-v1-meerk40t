#!/usr/bin/env python3
"""Red dot probe: cycle GPIO port bits to see which one (if any)
drives the aiming laser. NO list is executed and MO stays closed, so
the marking laser cannot fire."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller
from test_v1_meerk40t_real import FakeService

ctrl = V1Controller(FakeService())
ctrl.connect_if_needed()

print("WATCH THE MARKING HEAD - 2s per port bit, bit 8 twice (first + last)")
print()
for bit in (8, 0, 1, 2, 3, 4, 5, 6, 7, 8):
    print(f"port bit {bit} ON ...", flush=True)
    ctrl.port_set(0xFFFF, 0)       # clear all 16 bits
    ctrl.port_on(bit)
    ctrl.write_port()              # realtime 0x0021
    time.sleep(2.0)
    print("... OFF", flush=True)
    ctrl.port_set(0xFFFF, 0)
    ctrl.write_port()
    time.sleep(1.0)

ctrl.disconnect()
print()
print("Which bits lit a red dot? Tell me the number(s).")
