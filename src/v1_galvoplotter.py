#!/usr/bin/env python3
"""
V1 profile for galvoplotter - the translation layer that makes the
BJJCZ USBLM-V1 board (VID 9588 / PID 9999-9990) work with open-source
galvo software (MeerK40t and anything built on galvoplotter).

MIT library galvoplotter (github.com/meerk40t/galvoplotter) targets V2/V4
boards: PID 9899, commands on EP 0x02, 8-byte responses on EP 0x88.
The V1 board (verified by capture + probe) differs:

    V1 command : 14B = [0x0002, code, p1..p5] on EP 0x01
    V1 poll    :  2B = [0x0001]                on EP 0x01
    V1 list    : 3072B chunks                  on EP 0x02  (same as V2!)
    V1 response: 10B = 5 words LE              on EP 0x81
                 (galvoplotter expects 8B / 4 words -> first 8 bytes match)
    V1 status  : poll response w[3] = state; 0x0220 idle, 0x0224 running
                 (galvoplotter uses GetVersion bitmask -> must be overridden)
    V1 init    : exact EZCAD 2.5.3 sequence (verified)
    V1 lists   : buffer ALL chunks, then ExecuteList (0x0005) once at the end.
                 NO realtime SetEndOfList (0x0019) - chunks carry 0x8002
                 padding records already (galvoplotter pads with 0x8002 too!)

Usage:
    import v1_galvoplotter  # patches galvo.usb_connection for V1
    from galvo import GalvoController
    ctrl = V1GalvoController(x=0x8000, y=0x8000, ...)
    with ctrl.marking() as c:
        c.goto(0x5000, 0x5000)
        c.mark(0x5000, 0xA000)
        ...
    ctrl.wait_for_machine_idle()
"""
import os
import struct
import time

__version__ = "1.1.1"

import libusb_bootstrap  # noqa: F401 - MUST be before usb.core

import usb.core
import usb.util

import galvo.usb_connection as usb_connection
import galvo.controller as galvo_controller
from galvo.controller import GalvoController
from galvo.consts import (
    EnableLaser, Fiber_SetMo, GotoXY, WriteAnalogPort1, WritePort,
    listMarkTo,
)

VID_V1 = 0x9588
PID_V1 = 0x9999      # normal mode
PID_V1_LOADER = 0x9990
CMD_EP = 0x01        # commands / polls
RESP_EP = 0x81       # 10-byte responses
DATA_EP = 0x02       # 3072B list chunks

IDLE_STATE = 0x0220
RUNNING_STATE = 0x0224


class V1USBConnection(usb_connection.USBConnection):
    """V1 transport: dispatch commands/polls/lists to the right endpoints,
    read 10-byte responses, return the first 8 bytes galvoplotter expects."""

    def find_device(self, index=0):
        self.channel("Using LibUSB to connect (V1 profile).")
        dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            loader = usb.core.find(idVendor=VID_V1, idProduct=PID_V1_LOADER)
            if loader is not None:
                self.channel("Board in loader mode - uploading firmware...")
                import upload_firmware
                upload_firmware.upload()
                time.sleep(1.0)
                dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            self.channel("V1 board not found (need PID 9999).")
            raise ConnectionRefusedError
        self.devices[index] = dev
        self.channel(str(dev))
        return dev

    def write(self, index=0, packet=None, attempt=0):
        if packet is None:
            return
        n = len(packet)
        if n == 12:                       # galvoplotter command -> V1 command
            ep = CMD_EP
            data = b'\x02\x00' + packet   # 0x0002 prefix + code + 5 params
        elif n == 2:                      # V1 raw poll (status override)
            ep = CMD_EP
            data = packet
        elif n == 14:                     # raw 14-byte V1 command (init)
            ep = CMD_EP
            data = packet
        elif n == 4:                      # raw 4-byte V1 command (init)
            ep = CMD_EP
            data = packet
        elif n == 0xC00:                  # 3072B list chunk
            ep = DATA_EP
            data = packet
        else:
            raise ValueError(f"V1: unexpected packet size {n}")
        try:
            self.devices[index].write(endpoint=ep, data=data,
                                      timeout=self.timeout)
        except usb.core.USBError as e:
            # IMPORTANT: never close/open here - the V1 board drops to
            # loader mode on USB reset. Retry in place with backoff.
            if attempt <= 3:
                time.sleep(0.05 * (attempt + 1))
                self.write(index, packet, attempt + 1)
                return
            self.backend_error_code = e.backend_error_code
            self.channel(str(e))
            raise ConnectionError
        except KeyError:
            raise ConnectionError("Not Connected.")

    def read(self, index=0, attempt=0):
        try:
            r = bytes(self.devices[index].read(
                endpoint=RESP_EP, size_or_buffer=10, timeout=self.timeout))
            return r[:8]                  # galvoplotter unpacks '<4H' (8B)
        except usb.core.USBError as e:
            # Never close/open (USB reset kills the V1 board). Retry in place.
            if attempt <= 3:
                time.sleep(0.05 * (attempt + 1))
                return self.read(index, attempt + 1)
            self.backend_error_code = e.backend_error_code
            self.channel(str(e))
            raise ConnectionError
        except KeyError:
            raise ConnectionError("Not Connected.")


class V1GalvoController(GalvoController):
    """V1 behavior on top of galvoplotter's command layer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._first_mark = True

    def wait_ready(self):
        """Bounded wait: polls until idle (0x0220). If the board never
        reaches idle (e.g. stale 0x0226 list-open state), give up after
        5s so the flow can recover via the stop sequence."""
        t0 = time.time()
        while not self.is_ready():
            time.sleep(0.02)
            if not self._sending:
                return
            if time.time() - t0 > 5.0:
                return

    def _cpu_reset(self):
        """CPUCS reset - reboots the V1 firmware in place (PID stays
        9999). The one recovery that ALWAYS clears a wedged board.
        Do NOT bus-reset - that drops the board to loader mode."""
        try:
            dev = self.connection.devices.get(self._machine_index)
            if dev is None:
                return
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x01", timeout=500)
            time.sleep(0.1)
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x00", timeout=500)
        except Exception:
            pass

    def wait_idle(self):
        """Wait for the run to finish. Verified running states:
        0x0224 (vector) and 0x0234 (raster, power records) are both
        legitimate and are NEVER interrupted. Only provably-stuck
        states (0x0226 run-done, paused bit 0x08) get the stop
        sequence after 2s; CPUCS reboot + re-init as last resort.
        Safety net: 10 minutes absolute bound."""
        RUNNING = (0x0224, 0x0234)
        t0 = time.time()
        stuck_t0 = None
        while self.is_busy():
            time.sleep(0.02)
            if not self._sending:
                return
            if time.time() - t0 > 600.0:
                return
            st = self.status()
            if st in RUNNING:
                stuck_t0 = None
                continue
            if stuck_t0 is None:
                stuck_t0 = time.time()
            elif time.time() - stuck_t0 > 2.0:
                self._command(0x001F)     # StopExecute (verified)
                self.reset_list()         # 0x0012
                self._command(0x0021, 0)
                self._command(0x001D, 2000, 20, 1)
                self._command(0x0033, 0)
                time.sleep(0.3)
                st2 = self.status()
                if st2 in (0x0220, 0x0260):
                    return
                self._cpu_reset()
                time.sleep(0.8)
                try:
                    self.init_laser()     # re-init after firmware reboot
                except Exception:
                    pass
                return

    # ---------------- list records (EZCAD-identical flags) ----------------

    def list_mark(self, x, y, angle=0):
        """Mark record with EZCAD's flag word: 0x8000 on every mark except
        the first of the job (galvoplotter writes 0, which the V1 board
        does not treat as a laser-on mark)."""
        distance = int(abs(complex(x, y) - complex(self._last_x, self._last_y)))
        if distance > 0xFFFF:
            distance = 0xFFFF
        x = int(x)
        y = int(y)
        flag = 0 if self._first_mark else 0x8000
        self._list_write(listMarkTo, x, y, flag, distance)
        self._first_mark = False
        self._last_x = x
        self._last_y = y

    # ---------------- status (V1 polls, not GetVersion bitmask) -----------

    def status(self):
        """V1 poll: 2-byte 0x0001 on EP 0x01, state = w[3] of the 10-byte
        response (0x0220 idle / 0x0224 running / 0x0226 run-done-pending).
        Verifies the response is really a poll (w0==0x0001) - if a stale
        command response is read, keeps reading until the stream syncs.
        Never resets USB."""
        for _ in range(6):
            r = self.send(struct.pack('<H', 0x0001), read=True)
            if r is None or (isinstance(r, tuple) and r and r[0] == -1):
                time.sleep(0.01)
                continue
            if r[0] == 0x0001:            # genuine poll response
                return r[3]
            time.sleep(0.02)              # stale - drain and retry
        return None

    # is_ready/is_busy: base bit-mask semantics (READY=0x20, BUSY=0x04).
    # 0x0224/0x0226 both count as busy; idle is 0x0220 only.

    def is_ready(self):
        return self.is_ready_and_not_busy()

    def is_busy(self):
        status = self.status()
        return status is not None and bool(status & 0x04)  # BUSY bit

    def is_ready_and_not_busy(self):
        status = self.status()
        return status == IDLE_STATE

    def set_end_of_list(self, end):
        """0x0019 is not part of the V1 protocol; chunks already carry
        0x8002 end-of-list padding records (EZCAD-identical)."""
        return None

    def _list_end(self):
        """V1 buffered job model (proven v1_controller flow): progress
        handshake (0x0003 as 2-BYTE poll, as captured), queue the chunk,
        then DRAIN the chunk ack (the board answers every chunk write with
        a 0x0003 progress response - if unread it desyncs all later reads).
        ExecuteList fires via initial_configuration.
        The board's list buffer is finite: once full it stops reporting
        READY (0x0200) - execute the queued batch then, wait for it to
        finish, reset, and keep building (EZCAD raster streaming)."""
        with self._list_build_lock:
            if self._active_list and self._active_index:
                self.wait_ready()
                if self.is_busy():
                    # a previous run is still going - writing chunks into
                    # a busy board overwrites its list. Wait for it.
                    self.wait_idle()
                if not self.is_ready():
                    # board list buffer full -> run the queued batch now
                    self._flush_batch()
                while self.paused:
                    time.sleep(0.3)
                self.send(struct.pack('<H', 0x0003), read=True)  # 2B progress
                self.send(self._active_list, False)
                self._read_chunk_ack()
                self._number_of_list_packets += 1
                self._active_list = None
                self._active_index = 0

    def _flush_batch(self):
        """Execute the queued chunks as one mini-job (they form a
        complete list - the last chunk ends in 0x8002 padding), wait
        for the run to finish, and clear the board for the next batch."""
        if not self._number_of_list_packets:
            return
        self.execute_list()               # 0x0005
        self._command(0x0016, 1)          # SetControlMode(1)
        self._list_executing = True
        self.wait_idle()                  # let the batch run to completion
        self._list_executing = False
        self._number_of_list_packets = 0
        self.reset_list()                 # 0x0012 - clear the board

    def _read_chunk_ack(self):
        """Drain the board's response(s) to a 3072B chunk write (10-byte
        0x0003 progress responses). The ack latency is board-processing
        bound; short polling timeouts measured worse on Windows. Drain
        everything queued or later reads desync."""
        try:
            dev = self.connection.devices.get(self._machine_index)
            if dev is None:
                return None
        except AttributeError:
            return None
        time.sleep(0.02)                   # ack latency
        last = None
        while True:
            try:
                last = bytes(dev.read(endpoint=RESP_EP, size_or_buffer=10,
                                      timeout=15))
            except Exception:
                break                      # nothing more pending
        return last

    # ---------------- init (exact verified EZCAD 2.5.3 sequence) ----------

    def init_laser(self):
        self.usb_log("Initializing V1 laser (EZCAD 2.5.3 sequence)")
        self._command(0x0009)
        self._command(0x0007, 1)          # GetVersion(1)
        self.send(struct.pack('<2H', 0x0004, 0x0003), read=True)  # 4B variant
        self._command(0x0007, 1)
        self._command(0x0015)             # correction/config
        self._command(EnableLaser)        # 0x0004
        self._command(WriteAnalogPort1, 0x7FF)  # 0x0022 analog (init-only)
        self._command(0x0016, 0)          # SetControlMode(0)
        self._command(0x001B, 1)          # SetLaserMode(1)
        self._command(0x0017, 1)          # SetDelayMode(1)
        self._command(0x001C, 1)          # SetTiming(1)
        self._command(0x001D, 2000, 20, 1)  # SetStandby
        self._command(0x001A, 200)        # SetFirstPulseKiller
        self._command(0x001E, 50)         # SetPwmHalfPeriod
        self._command(0x0006, 50)         # SetPwmPulseWidth
        self._command(Fiber_SetMo, 0)     # 0x0033 MO closed
        self.wait_ready()
        self._command(0x0062, 0x0FFB, 1, 0x0199, 100)  # FPK params
        self._command(0x0007, 1)
        self.send(struct.pack('<7H', 0x0006, 0x0032, 0, 0x00A3, 0x03E8,
                              0x0019, 0), read=True)   # fly res (raw 14B)
        self._command(WritePort, 0)       # 0x0021(0)
        self._command(0x003A)             # EnableZ
        self.wait_ready()
        self.usb_log("V1 laser initialized")

    def _clear_pause(self):
        """If the board is PAUSED (bit 0x08 - a StopList landed during a
        previous run), StopExecute (0x001F, verified) clears it back to
        0x0220. RestartList would RESUME the stale paused list - never
        use it here. A paused board ignores new lists and resumes the
        OLD one."""
        st = self.status()
        if st is not None and (st & 0x08):
            self._command(0x001F)

    def initial_configuration(self):
        """End of run - PROVEN v1_controller sequence (from test_fill3d):
        execute, SetControlMode(1), poll until state 0x0220, home to center.
        No EZCAD stop sequence needed - the board returns to idle by itself
        (verified: IDLE after 0.13s)."""
        if self.laser_configuration == "initial":
            return
        self.list_end_of_list()          # ensure at least one end-of-list
        self._list_end()
        if not self._list_executing and self._number_of_list_packets:
            self._clear_pause()
            self.execute_list()          # 0x0005 (response read promptly)
            self._command(0x0016, 1)     # SetControlMode(1)
        self._list_executing = False
        self._number_of_list_packets = 0
        self.wait_idle()                 # poll until state 0x0220
        if self.source == "fiber":
            self.set_fiber_mo(0)         # 0x0033 MO close
        self.goto_xy(0x8000, 0x8000)     # home galvo to center
        marktime = self.get_mark_time()
        self.usb_log(f"Time taken for list execution: {marktime}")
        self.laser_configuration = "initial"

    def lighting_configuration(self):
        """V1 lighting (outline/red dot): same verified transition as
        marking_configuration, light pin port only (laser pin OFF)."""
        if self.laser_configuration == "lighting":
            return
        if self.laser_configuration == "marking":
            if self.source == "fiber":
                self.set_fiber_mo(0)
            self.port_off(self.laser_pin)
            self.port_on(self.light_pin)
            self.write_port()
        else:
            self._ready = None
            self._speed = None
            self._travel_speed = None
            self._frequency = None
            self._power = None
            self._pulse_width = None
            self._delay_jump = None
            self._delay_on = None
            self._delay_off = None
            self._delay_poly = None
            self._delay_end = None
            self.port_off(bit=self.laser_pin)   # laser OFF during outlining
            self.port_on(self.light_pin)
            # V1 verified transition (same as marking_configuration)
            self._command(0x0009)
            self._command(0x0034)
            self.wait_ready()
            self.reset_list()
            self._command(0x000C)
            self.goto_xy(0x8001, 0x8001)
            self.wait_ready()
            self.list_write_port()        # 0x8011 (light bit only)
            if self.light_speed is not None:
                self.list_jump_speed(self._convert_speed(self.light_speed))
            else:
                self.list_jump_speed(0x0D1B)   # guaranteed speed record
            self.list_ready()             # 0x8051
        self.laser_configuration = "lighting"

    def abort(self, dummy_packet=True):
        """V1 abort: StopExecute (0x001F, verified) - clean stop back to
        0x0220. StopList (0x0020) leaves the board PAUSED (0x238), which
        stalls later behavior. Clear buffers, no dummy empty-list execute."""
        with self._list_build_lock:
            self._command(0x001F)         # StopExecute - clean stop
            if self.source == "fiber":
                self.set_fiber_mo(0)
            self.reset_list()
            self._list_new()
            self._list_executing = False
            self._number_of_list_packets = 0
            if self.source == "fiber":
                self.set_fiber_mo(0)
            self.port_off(self.laser_pin)
            self.write_port()
            self.laser_configuration = "initial"

    def write_correction_file(self, filename):
        """V1: the 0x0015 cor-table payload format is undecoded - refuse
        instead of sending garbage to the board."""
        self.usb_log("Correction file upload is not supported on the V1 board.")
        return None

    def write_blank_correct_file(self):
        self.usb_log("Correction file upload is not supported on the V1 board.")
        return None

    # ---------------- per-run transition (verified) ------------------------

    def marking_configuration(self):
        if self.laser_configuration == "marking":
            return
        if self.laser_configuration == "lighting":
            self.laser_configuration = "marking"
            self.port_on(bit=self.laser_pin)
            self.light_off()
            if self.source == "fiber":
                self.set_fiber_mo(1)
        else:
            self.laser_configuration = "marking"
            self._ready = None
            self._speed = None
            self._travel_speed = None
            self._frequency = None
            self._power = None
            self._pulse_width = None
            self._delay_jump = None
            self._delay_on = None
            self._delay_off = None
            self._delay_poly = None
            self._delay_end = None
            self._first_mark = True
            self.port_on(bit=self.laser_pin)   # 0x8011 listWritePort = 1
            # V1 verified transition (buffered job model, from test_fill3d)
            self._command(0x0009)
            self._command(0x0034)
            self.wait_ready()
            self.reset_list()             # 0x0012
            self._command(0x000C)
            self.goto_xy(0x8001, 0x8001)  # 0x000D home corner (as captured)
            if self.source == "fiber":
                self.set_fiber_mo(1)      # 0x0033 MO open
            self.wait_ready()
            self.list_ready()             # 0x8051
            self.list_delay_time(int(self.delay_open_mo * 100))  # 0x0320
            self.list_write_port()        # 0x8011 (port bits = laser pin)
        self.set()


def patch():
    """Make galvo.usb_connection.USBConnection resolve to the V1 transport.
    controller.py imports the class by name, so patch both namespaces."""
    usb_connection.USBConnection = V1USBConnection
    galvo_controller.USBConnection = V1USBConnection


patch()


if __name__ == "__main__":
    print("V1 galvoplotter profile loaded (patched usb_connection).")
