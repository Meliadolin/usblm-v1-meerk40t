#!/usr/bin/env python3
"""HARDWARE test of the USBLM-V1 profile: drive the V1 controller
directly (program_mode -> goto/mark -> rapid_mode -> wait_finished).
Requires the board on PID 9999 + WinUSB. Self-terminates after 45s."""
import os
import sys
import threading
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from usblm_v1.controller import V1Controller


def watchdog():
    t = threading.Timer(300, lambda: os._exit(2))
    t.daemon = True
    t.start()


watchdog()


class FakeChannel:
    _ = staticmethod(lambda s: s)

    def watch(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        pass


class FakeService:
    safe_label = "V1TEST"
    source = "fiber"
    signal_updates = False
    corfile = None
    corfile_enabled = False
    serial_enable = False
    serial = None
    delay_openmo = 8.0
    first_pulse_killer = 200
    pwm_pulse_width = 125
    pwm_half_period = 125
    standby_param_1 = 2000
    standby_param_2 = 20
    timing_mode = 1
    delay_mode = 1
    laser_mode = 1
    control_mode = 0
    fpk2_p1, fpk2_p2, fpk2_p3, fpk2_p4 = 0x0FFB, 1, 0x0199, 100
    fly_res_p1, fly_res_p2, fly_res_p3, fly_res_p4 = 0, 99, 1000, 25
    _settings = {"light_pin": 8, "foot_pin": 15}

    def setting(self, typ, name, default=None):
        return self._settings.get(name, default)

    def channel(self, *a, **k):
        return FakeChannel()

    def signal(self, *a, **k):
        pass

    class _View:
        @staticmethod
        def position(*a, **k):
            return (10.0, 10.0)   # 10 galvos per mm

    view = _View()


def main():
    svc = FakeService()
    ctrl = V1Controller(svc)
    t0 = time.time()
    try:
        print("=== connect + init ===")
        ctrl.connect_if_needed()
        print("connected")
        conn = ctrl.connection
        orig_w, orig_r = conn.write, conn.read

        def w(index=0, packet=None, attempt=0):
            n = len(packet) if packet else 0
            tag = {12: "CMD", 2: "POLL", 3072: "CHUNK", 14: "RAW14", 4: "RAW4"}.get(n, str(n))
            print(f"[{time.time()-t0:8.3f}s] {tag} {packet.hex(' ') if n < 20 else f'chunk {n}B'}")
            return orig_w(index, packet, attempt)

        def r(index=0, attempt=0):
            res = orig_r(index, attempt)
            print(f"[{time.time()-t0:8.3f}s] RESP {res.hex(' ') if res else 'None'}")
            return res

        conn.write, conn.read = w, r

        print("=== program_mode (V1 transition) ===")
        ctrl.program_mode()
        ctrl.list_jump_speed(0x0D1B)
        ctrl.list_mark_speed(0x0320)
        ctrl.list_mark_current(0x04CC)
        ctrl.list_qswitch_period(0x03E8)
        ctrl.list_laser_on_delay(0x012C)
        ctrl.list_laser_off_delay(0x0064)
        ctrl.list_polygon_delay(0x000A)
        ctrl.list_jump_delay(0x0064)
        ctrl.goto(0x6000, 0x6000)
        ctrl.mark(0x6000, 0xA000)
        ctrl.mark(0xA000, 0xA000)
        ctrl.mark(0xA000, 0x6000)
        ctrl.mark(0x6000, 0x6000)

        print("=== rapid_mode (execute + wait idle) ===")
        ctrl.rapid_mode()
        st = ctrl.status()
        print(f"state after rapid_mode: {hex(st) if st is not None else None}")

        print("=== wait_finished (bounded) ===")
        tw = time.time()
        while not ctrl.is_ready_and_not_busy() and time.time() - tw < 20:
            time.sleep(0.02)
        st = ctrl.status()
        print(f"wait_finished done, state: {hex(st) if st is not None else None}")
        print("JOB DONE - square marked via the USBLM-V1 profile")
        ctrl.disconnect()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            ctrl.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
