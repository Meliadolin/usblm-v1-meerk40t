#!/usr/bin/env python3
"""OFFLINE test of the V1 galvoplotter profile with a fake board transport.
No hardware needed. Validates: connect flow, init_laser, marking_configuration,
list building, chunk flush, execute-once, busy->idle wait."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import v1_galvoplotter
from v1_galvoplotter import V1GalvoController


class FakeConnection:
    """Simulated V1 board: accepts any packet, replies 10-byte responses.
    State machine: idle 0x0220; goes RUNNING on ExecuteList (0x0005),
    back to idle after 3 polls (simulating a short job)."""

    def __init__(self, channel=None):
        self._log = channel
        self.devices = {}
        self.interface = {}
        self.backend_error_code = None
        self.timeout = 500
        self._busy_polls = 0
        self.cmds = []
        self.chunks = []

    def channel(self, data):
        pass

    def is_open(self, index=0):
        return index in self.devices

    def open(self, index=0):
        self.devices[index] = True
        return index

    def close(self, index=0):
        self.devices.pop(index, None)

    def write(self, index=0, packet=None, attempt=0):
        n = len(packet)
        if n == 12:
            code = struct.unpack('<H', packet[:2])[0]
            self.cmds.append(code)
            if code == 0x0005:          # ExecuteList -> start running
                self._busy_polls = 3
        elif n == 0xC00:
            self.chunks.append(packet)

    def read(self, index=0, attempt=0):
        if self._busy_polls > 0:
            self._busy_polls -= 1
            state = 0x0224
        else:
            state = 0x0220
        return struct.pack('<4H', 0x0001, 0x0001, 0, state)  # 8B (profile output)

    def dump(self):
        from galvo.consts import single_command_lookup
        out = []
        for code in self.cmds:
            out.append(f"  {code:04x} {single_command_lookup.get(code, '')}")
        return "\n".join(out)


def main():
    ctrl = V1GalvoController(
        x=0x8000, y=0x8000,
        mark_speed=200.0,
        travel_speed=2000.0,
        power=30.0,
        frequency=20.0,
        delay_open_mo=8.0,
    )
    fake = FakeConnection()
    ctrl.connection = fake

    print("=== connect (fake board) ===")
    ctrl.connect_if_needed()
    print("commands sent during connect:")
    print(fake.dump())
    assert fake.cmds.count(0x0004) >= 1, "EnableLaser missing"
    assert 0x0022 in fake.cmds, "WriteAnalogPort1 missing"

    print("\n=== marking a square ===")
    with ctrl.marking() as c:
        c.goto(0x5000, 0x5000)
        c.mark(0x5000, 0xA000)
        c.mark(0xA000, 0xA000)
        c.mark(0xA000, 0x5000)
        c.mark(0x5000, 0x5000)

    print("\n=== wait idle (board busy -> idle) ===")
    ctrl.wait_for_machine_idle()

    n_chunks = len(fake.chunks)
    print(f"\n=== done: {n_chunks} chunk(s) queued ===")
    assert n_chunks >= 1, "no list chunks sent"
    assert fake.cmds.count(0x0005) == 1, "ExecuteList must fire exactly once"
    assert 0x0019 not in fake.cmds, "SetEndOfList (0x0019) must not be sent"
    print("chunk[0] first records:")
    c0 = fake.chunks[0]
    for i in range(0, 72, 12):
        w = struct.unpack('<6H', c0[i:i+12])
        print(f"   {w[0]:04x} x={w[1]:04x} y={w[2]:04x} m={w[3]:04x} d={w[4]:04x}")
    tail = c0[-12:]
    w = struct.unpack('<6H', tail)
    assert w[0] == 0x8002, f"chunk tail must be 0x8002 padding, got {w[0]:04x}"
    print(f"   ... tail: {w[0]:04x} (0x8002 end-of-list padding)")
    print("\nOFFLINE TEST PASSED")
    ctrl.disconnect()


if __name__ == "__main__":
    main()
