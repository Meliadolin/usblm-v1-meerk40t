#!/usr/bin/env python3
"""
V1 profile for MeerK40t (balormk plugin) - makes the free cross-platform
GUI laser software drive the BJJCZ USBLM-V1 board (VID 9588 / PID 9999).

MeerK40t embeds its own galvoplotter fork (meerk40t.balormk) with V2/V4
defaults (PID 9899, EP 0x02/0x88, 8-byte reads). This module patches it
for the V1 board, exactly like v1_galvoplotter.py does for the standalone
library:

  V1 command : 14B = [0x0002, code, p1..p5] on EP 0x01
  V1 poll    :  2B = [0x0001]                on EP 0x01
  V1 list    : 3072B chunks                  on EP 0x02
  V1 response: 10B = 5 words LE              on EP 0x81 (return first 8)
  V1 status  : poll w[3] = state; 0x0220 idle / 0x0224 running
  V1 chunks  : every chunk write gets a 0x0003 progress ACK on EP 0x81
               - must be drained or all later reads desync
  V1 lists   : buffer all chunks, ExecuteList (0x0005) once at the end

Usage:
    import v1_meerk40t   # BEFORE starting the GUI / creating the device
"""
import os
import re
import struct
import sys
import time
from math import isinf

import numpy as np

__version__ = "1.1.0"

import libusb_bootstrap  # noqa: F401 - MUST be before usb.core

import usb.core
import usb.util

import meerk40t.balormk.usb_connection as mk_usb
import meerk40t.balormk.controller as mk_ctrl
import meerk40t.balormk.driver as mk_driver
from meerk40t.core.geomstr import Geomstr
from meerk40t.core.node.node import Node

# ------------------------------------------------------------------
# progress tracing: logs\v1_shim_trace.log in the package root
# (next to the exe when frozen, else two levels up from this file)
# ------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _TRACE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _TRACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRACE_DIR = os.path.join(_TRACE_DIR, "logs")
os.makedirs(_TRACE_DIR, exist_ok=True)
_TRACE_PATH = os.path.join(_TRACE_DIR, "v1_shim_trace.log")


def _trace(msg):
    try:
        with open(_TRACE_PATH, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _scan_windows_usb():
    """Windows-side check for the board. libusb's WinUSB backend cannot
    see a device that has NO driver bound - this scans the Windows
    device tree via pnputil and reports the real state."""
    import subprocess
    try:
        out = subprocess.run(["pnputil", "/enum-devices"],
                             capture_output=True, text=True, timeout=30)
        text = out.stdout
    except Exception as e:
        _trace(f"_scan_windows_usb: pnputil failed: {e}")
        return
    blocks = text.split("Instance ID:")
    for b in blocks[1:]:
        if "VID_9588" in b:
            pid = ""
            desc = ""
            driver = ""
            for line in b.splitlines()[:8]:
                if "PID_" in line:
                    m = re.search(r"PID_([0-9A-Fa-f]{4})", line)
                    if m:
                        pid = m.group(1)
                if "Description:" in line:
                    desc = line.split(":", 1)[1].strip()
                if "Driver Name:" in line:
                    driver = line.split(":", 1)[1].strip()
            state = "WINUSB-BOUND" if driver else "NO-DRIVER (invisible to libusb)"
            msg = (f"board in Windows device tree: PID_{pid} "
                   f"'{desc}' driver='{driver}' -> {state}")
            print(msg)
            _trace(msg)
            if not driver:
                print("  FIX: install the WinUSB driver - run scripts\\bind_winusb.cmd "
                      "(or SetupPanel button 2)")
                _trace("  FIX: install the WinUSB driver - run scripts\\bind_winusb.cmd")

VID_V1 = 0x9588
PID_V1 = 0x9999
PID_V1_LOADER = 0x9990
CMD_EP = 0x01
RESP_EP = 0x81
DATA_EP = 0x02

IDLE_STATE = 0x0220


class V1MKConnection(mk_usb.USBConnection):
    """V1 transport: dispatch commands/polls/chunks to the right endpoints,
    read 10-byte responses, return the first 8 bytes MeerK40t expects."""

    def find_device(self, index=0):
        self.channel("Using LibUSB to connect (V1 profile).")
        _trace("find_device: searching PID 9999")
        dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            loader = usb.core.find(idVendor=VID_V1, idProduct=PID_V1_LOADER)
            if loader is not None:
                self.channel("Board in loader mode - uploading firmware...")
                _trace("find_device: loader mode (9990) - uploading firmware")
                import upload_firmware
                upload_firmware.upload()
                time.sleep(1.0)
                _trace("find_device: waiting for re-enumeration")
                dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            self.channel("V1 board not found (need PID 9999).")
            _trace("find_device: FAIL - board not found via libusb")
            _scan_windows_usb()
            raise ConnectionRefusedError
        self.devices[index] = dev
        _trace(f"find_device: OK bus={dev.bus} addr={dev.address}")
        self.channel(str(dev))
        return dev

    def disconnect_reset(self, device, interface=0):
        """V1 boards drop into loader mode (PID 9990) on a USB bus
        reset. balormk's close() resets by default - the V1 must not.
        (The firmware survives; loader mode just needs a re-upload.)"""

    def write(self, index=0, packet=None, attempt=0):
        if packet is None:
            return
        n = len(packet)
        if n == 12:                       # command -> V1 command
            ep = CMD_EP
            data = b"\x02\x00" + packet   # 0x0002 prefix
        elif n == 2:                      # raw 2B poll / progress
            ep = CMD_EP
            data = packet
        elif n in (4, 14):                # raw V1 commands (init)
            ep = CMD_EP
            data = packet
        elif n == 0xC00:                  # list chunk
            ep = DATA_EP
            data = packet
        else:
            raise ValueError(f"V1: unexpected packet size {n}")
        try:
            self.devices[index].write(endpoint=ep, data=data,
                                      timeout=self.timeout)
        except usb.core.USBError as e:
            # NEVER close/open here - USB reset drops the V1 board to
            # loader mode. Retry in place with backoff.
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
            return r[:8]
        except usb.core.USBError as e:
            if attempt <= 3:
                time.sleep(0.05 * (attempt + 1))
                return self.read(index, attempt + 1)
            self.backend_error_code = e.backend_error_code
            self.channel(str(e))
            raise ConnectionError
        except KeyError:
            raise ConnectionError("Not Connected.")


class V1MKController(mk_ctrl.GalvoController):
    """V1 behavior on top of MeerK40t's balormk controller."""

    # The V1 board is a fiber driver board - force fiber source even if
    # the device was created as CO2/UV (they use wrong power records).
    @property
    def source(self):
        return "fiber"

    def wait_finished(self):
        """Bounded: 20s max (balormk's loops forever)."""
        t0 = time.time()
        while not self.is_ready_and_not_busy():
            time.sleep(0.02)
            if time.time() - t0 > 20.0:
                return

    def status(self):
        """V1 poll: 2-byte 0x0001, state = w[3] (0x0220 idle).
        Verifies the response is really a poll (w0==0x0001) - if a stale
        command response is read, keeps reading until the stream syncs."""
        for _ in range(6):
            r = self.send(struct.pack("<H", 0x0001), read=True)
            if r is None or (isinstance(r, tuple) and r and r[0] == -1):
                time.sleep(0.01)
                continue
            if r[0] == 0x0001:            # genuine poll response
                return r[3]
            time.sleep(0.02)              # stale - drain and retry
        _trace("status: FAIL - no valid poll response after 6 tries")
        return None

    # is_ready/is_busy/is_ready_and_not_busy: base bit-mask semantics
    # (READY=0x20, BUSY=0x04) - overridden to be None-safe (a missing
    # board makes status() return None; the base class crashes on None).

    def is_ready(self):
        status = self.status()
        return status is not None and bool(status & 0x20)

    def is_busy(self):
        status = self.status()
        return status is not None and bool(status & 0x04)

    def is_ready_and_not_busy(self):
        status = self.status()
        return (status is not None and bool(status & 0x20)
                and not bool(status & 0x04))

    def set_end_of_list(self, end):
        """0x0019 not part of the V1 protocol; chunks carry 0x8002."""
        return None

    def _list_end(self):
        """V1 buffered model: queue chunk + drain its ACK; no
        set_end_of_list, no mid-stream execute (rapid_mode fires it).
        BUT: the board's internal list buffer is finite - once full it
        stops reporting READY (state 0x0200). When that happens mid-
        build, execute what is already queued (a complete mini-list,
        the last chunk ends in 0x8002 padding), wait for it to finish,
        reset, and keep building - the EZCAD raster streaming model."""
        if not self._active_list or not self._active_index:
            return
        with self._list_lock:
            if not self._active_list or not self._active_index:
                return
            self.wait_ready()
            if self.is_busy():
                # a previous run (e.g. a light pass) is still going -
                # writing chunks into a busy board overwrites its list.
                # Wait for it to finish before building further.
                self.wait_idle()
            if not self.is_ready():
                # board list buffer full -> run the queued batch now
                _trace("_list_end: board not ready (buffer full) - "
                       "executing queued batch")
                self._flush_batch()
            while self.paused:
                time.sleep(0.3)
            self.send(struct.pack("<H", 0x0003), read=True)  # progress handshake
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
        self._clear_pause()
        self.execute_list()               # 0x0005
        self._command(0x0016, 1)          # SetControlMode(1)
        self._list_executing = True
        self.wait_idle()                  # let the batch run to completion
        self._list_executing = False
        self._number_of_list_packets = 0
        self.reset_list()                 # 0x0012 - clear the board
        _trace("_flush_batch: batch executed and cleared")

    def _read_chunk_ack(self):
        """The board answers each chunk write with a 10-byte 0x0003
        progress response. Drain EVERYTHING queued or later reads
        desync. The ack latency is board-processing bound (power-heavy
        records take longer); short polling timeouts measured WORSE on
        Windows (timer granularity), so a fixed wait + short reads."""
        try:
            dev = self.connection.devices.get(self._machine_index)
            if dev is None:
                return None
        except (KeyError, AttributeError):
            return None
        time.sleep(0.02)                   # ack latency
        last = None
        while True:
            try:
                last = bytes(dev.read(endpoint=RESP_EP, size_or_buffer=10,
                                      timeout=15))
            except usb.core.USBError:
                break                      # nothing more pending
        return last

    def wait_ready(self):
        """Bounded: 5s max. balormk's version loops forever."""
        t0 = time.time()
        while not self.is_ready():
            time.sleep(0.02)
            if time.time() - t0 > 5.0:
                _trace("wait_ready: TIMEOUT after 5s")
                return

    def _cpu_reset(self):
        """CPUCS reset - reboots the V1 firmware in place (PID stays
        9999). The one recovery that ALWAYS clears a wedged board
        (e.g. stuck waiting for an input that never comes). Do NOT
        bus-reset - that drops the board to loader mode."""
        try:
            dev = self.connection.devices.get(self._machine_index)
            if dev is None:
                return
            _trace("_cpu_reset: CPUCS toggle (0xE600)")
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x01", timeout=500)
            time.sleep(0.1)
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x00", timeout=500)
        except Exception as e:
            _trace(f"_cpu_reset FAILED: {e}")

    def wait_idle(self):
        """Wait for a run to finish. Verified running states:
          0x0224 = vector list running (no power records)
          0x0234 = raster-style list running (power records present)
        BOTH are legitimate and are NEVER interrupted - a raster job
        can legitimately run for minutes. Only provably-stuck states
        get the stop sequence after 2s:
          0x0226 (run-done, list still open) and the PAUSED bit (0x08).
        Safety net: 10 minutes absolute bound (any real job finishes)."""
        RUNNING = (0x0224, 0x0234)
        t0 = time.time()
        stuck_t0 = None
        while self.is_busy():
            time.sleep(0.02)
            if time.time() - t0 > 600.0:
                _trace("wait_idle: GLOBAL TIMEOUT after 10 min")
                return
            st = self.status()
            if st in RUNNING:
                stuck_t0 = None
                continue
            if stuck_t0 is None:
                stuck_t0 = time.time()
            elif time.time() - stuck_t0 > 2.0:
                _trace(f"wait_idle: stuck at {hex(st) if st else 'None'} "
                       "(not a running state) - stop sequence")
                self._command(0x001F)     # StopExecute (verified)
                self.reset_list()         # 0x0012
                self._command(0x0021, 0)
                self._command(0x001D, 2000, 20, 1)
                self._command(0x0033, 0)
                time.sleep(0.3)
                st2 = self.status()
                if st2 in (0x0220, 0x0260):
                    return
                _trace(f"wait_idle: still stuck at "
                       f"{hex(st2) if st2 else 'None'} - CPUCS reboot")
                self._cpu_reset()
                time.sleep(0.8)
                try:
                    self.init_laser()     # re-init after firmware reboot
                except Exception as e:
                    _trace(f"wait_idle: re-init failed: {e}")
                return

    def init_laser(self):
        """V1 verified EZCAD 2.5.3 init (balormk's sends 0x0040 Reset +
        serial query which the V1 board does not use)."""
        _trace("init_laser: start (V1 EZCAD 2.5.3 sequence)")
        self.usb_log("Initializing V1 laser (EZCAD 2.5.3 sequence)")
        self._command(0x0009)
        self._command(0x0007, 1)          # GetVersion(1)
        self.send(struct.pack("<2H", 0x0004, 0x0003), read=True)
        self._command(0x0007, 1)
        self._command(0x0015)             # correction/config
        self._command(0x0004)             # EnableLaser
        self._command(0x0022, 0x7FF)      # WriteAnalogPort1
        self._command(0x0016, 0)          # SetControlMode(0)
        self._command(0x001B, 1)          # SetLaserMode(1)
        self._command(0x0017, 1)          # SetDelayMode(1)
        self._command(0x001C, 1)          # SetTiming(1)
        self._command(0x001D, 2000, 20, 1)  # SetStandby
        self._command(0x001A, 200)        # SetFirstPulseKiller
        self._command(0x001E, 50)         # SetPwmHalfPeriod
        self._command(0x0006, 50)         # SetPwmPulseWidth
        self._command(0x0033, 0)          # Fiber_SetMo closed
        self.wait_ready()
        self._command(0x0062, 0x0FFB, 1, 0x0199, 100)  # FPK params
        self._command(0x0007, 1)
        self.send(struct.pack("<7H", 0x0006, 0x0032, 0, 0x00A3, 0x03E8,
                              0x0019, 0), read=True)
        self._command(0x0021, 0)          # WritePort(0)
        self._command(0x003A)             # EnableZ
        self.wait_ready()
        self.usb_log("V1 laser initialized")
        _trace("init_laser: done")

    def rapid_mode(self):
        """V1 end-of-run: execute once + SetControlMode(1) right after
        (missing from balormk - without it the board stays at 0x0226),
        wait idle, MO close, port clear, return galvo to center
        (EZCAD end-of-run sends 0x000D(0x8000,0x8000))."""
        if self.mode == mk_ctrl.DRIVER_STATE_RAPID:
            self._clear_pause()
            return
        self.list_end_of_list()
        self._list_end()
        if not self._list_executing and self._number_of_list_packets:
            _trace(f"rapid_mode: executing list ({self._number_of_list_packets} packet(s))")
            self._clear_pause()
            self.execute_list()
            self._command(0x0016, 1)      # SetControlMode(1)
        self._list_executing = False
        self._number_of_list_packets = 0
        self.wait_idle()
        st = self.status()
        _trace(f"rapid_mode: idle, state={hex(st) if st is not None else 'None'}")
        self.mode_shift(0)
        self.port_off(bit=0)
        self.write_port()
        self.goto_xy(0x8000, 0x8000)      # auto-home: galvo to center
        marktime = self.get_mark_time()
        self.service.signal("galvo;marktime", marktime)
        self.usb_log(f"Time taken for list execution: {marktime}")
        self.mode = mk_ctrl.DRIVER_STATE_RAPID

    def abort(self, dummy_packet=True):
        """V1 abort: StopExecute (0x001F, verified) - it stops the run
        cleanly back to 0x0220. StopList (0x0020) would leave the board
        PAUSED (state 0x238), which stalls later behavior. Clear both
        the board and the controller list buffer, no dummy empty-list
        execute (the V1 board would actually run it)."""
        if self.mode == mk_ctrl.DRIVER_STATE_RAW:
            return
        self._command(0x001F)         # StopExecute - clean stop
        self.paused = False
        self.set_fiber_mo(0)
        self.reset_list()
        self._list_new()
        self._list_executing = False
        self._number_of_list_packets = 0
        self.set_fiber_mo(0)
        self.port_off(bit=0)
        self.write_port()
        self.mode = mk_ctrl.DRIVER_STATE_RAPID

    def _clear_pause(self):
        """If the board is PAUSED (bit 0x08 - a StopList landed during a
        previous run), StopExecute (0x001F, verified) clears it back to
        0x0220. RestartList would RESUME the stale paused list - never
        use it here. A paused board ignores new lists and resumes the
        OLD one (the 'text engraved again' bug)."""
        st = self.status()
        if st is not None and (st & 0x08):
            _trace(f"_clear_pause: state {hex(st)} - StopExecute")
            self._command(0x001F)

    def write_correction_file(self, filename):
        """V1: the 0x0015 cor-table payload format is undecoded - refuse
        instead of sending garbage to the board."""
        _trace("write_correction_file: not supported on V1 (0x0015 payload unknown)")
        self.usb_log("Correction file upload is not supported on the V1 board.")
        return None

    def write_blank_correct_file(self):
        _trace("write_blank_correct_file: not supported on V1")
        return None

    def light_mode(self):
        """V1 light/outline mode (red-dot continuous tracing).
        Fixes the three V1 gaps in balormk's version:
        1. V1 transition (0x0009, 0x0034, ...) - the board needs it
        2. a jump speed record - balormk never sends one when
           light_speed is None (galvo then runs at max speed)
        3. configurable light pin (service.light_pin, default 8)"""
        if self.mode == mk_ctrl.DRIVER_STATE_LIGHT:
            self._clear_pause()
            return
        if self.mode == mk_ctrl.DRIVER_STATE_PROGRAM:
            self.mode_shift(0)
            self.port_off(bit=0)
            self.port_on(self._light_bit)
            self.write_port()
        else:
            self.mode = mk_ctrl.DRIVER_STATE_LIGHT
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
            # V1 transition (verified, same as program_mode)
            self._command(0x0009)
            self._command(0x0034)
            self.wait_ready()
            self.reset_list()             # 0x0012
            self._command(0x000C)
            self.goto_xy(0x8001, 0x8001)  # 0x000D home corner
            self.wait_ready()
            self.port_off(bit=0)          # laser pin OFF during outlining
            self.port_on(self._light_bit)
            self.list_write_port()        # 0x8011 with light bit only
            # guaranteed light speed record (0x8006)
            try:
                light_speed = int(self.service.redlight_speed)
                self.list_jump_speed(self._convert_speed(light_speed))
            except Exception:
                self.list_jump_speed(0x0D1B)   # fallback 3355
            self.list_ready()             # 0x8051

    def v1_execute_light_list(self):
        """Execute one full light-trace pass (buffered job model) and wait
        for the board to finish. The V1 board cannot append records while
        executing, so each live-trace pass is its own buffered job.
        Ends the list EXACTLY like rapid_mode does: an 0x8002 end-of-list
        record + terminator chunk before ExecuteList - without it the
        board never sees the list as complete and waits forever (0x234)."""
        if not self._number_of_list_packets and not self._active_index:
            return
        self.list_end_of_list()       # 0x8002 end-of-list record
        self._list_end()              # flush terminator chunk (like rapid_mode)
        if not self._number_of_list_packets:
            return
        _trace(f"light pass: executing {self._number_of_list_packets} packet(s)")
        self._clear_pause()
        self.execute_list()
        self._command(0x0016, 1)
        self._list_executing = True
        t0 = time.time()
        while self.is_busy():
            time.sleep(0.02)
            if time.time() - t0 > 10.0:
                _trace("light pass: idle wait TIMEOUT after 10s")
                break
        self._list_executing = False
        self._number_of_list_packets = 0

    def program_mode(self):
        """V1 verified per-run transition (0x0009, 0x0034, ResetList,
        0x000C, home corner, MO open) then the standard list setup.
        Even when already in PROGRAM mode, a possible PAUSED board is
        cleared and the list reset - a paused board would otherwise
        absorb the new chunks into its STALE list."""
        if self.mode == mk_ctrl.DRIVER_STATE_PROGRAM:
            self._clear_pause()
            self.reset_list()
            return
        if self.mode == mk_ctrl.DRIVER_STATE_LIGHT:
            self.mode = mk_ctrl.DRIVER_STATE_PROGRAM
            self.light_off()
            self.port_on(bit=0)
            self.write_port()
            self.mode_shift(1)
        else:
            self.mode = mk_ctrl.DRIVER_STATE_PROGRAM
            _trace("program_mode: V1 transition (0x0009, 0x0034, ...)")
            # V1 verified transition (buffered job model)
            if self.is_busy():
                # a previous run (light pass, prior job) must finish first
                self.wait_idle()
            self._clear_pause()
            self._command(0x0009)
            self._command(0x0034)
            self.wait_ready()
            self.reset_list()             # 0x0012
            self._command(0x000C)
            self.goto_xy(0x8001, 0x8001)  # 0x000D home corner
            self.wait_ready()
            self.port_on(bit=0)           # laser pin for 0x8011 record
            self.mode_shift(1)            # 0x0033(1) MO open (fiber)
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
            self.list_ready()             # 0x8051
            if self.source == "fiber":
                if self.service.delay_openmo != 0:
                    self.list_delay_time(int(self.service.delay_openmo * 100))
            elif self.source == "co2":
                pass
            self.list_write_port()        # 0x8011


def _v1_trace_redlight(self, con):
    """V1 live-trace pass: build the ENTIRE path as one buffered list,
    then execute it once and wait for the board to finish (balormk's
    version streams records mid-execution - the V1 board overwrites its
    buffer, so nothing would ever run)."""
    con.light_mode()
    delay_dark = self.service.redlight_delay_dark
    delay_between = self.service.redlight_delay_light
    move = True
    first = True
    first_x, first_y = None, None
    for i, e in enumerate(self.points):
        if self.stopped or self.changed:
            return
        if e is None:
            move = True
            continue
        x, y = e.real, e.imag
        if np.isnan(x) or np.isnan(y):
            move = True
            continue
        x = int(x)
        y = int(y)
        if x < 0 or x > 0xFFFF or y < 0 or y > 0xFFFF:
            if self.bounded:
                continue
            x = max(min(x, 0xFFFF), 0)
            y = max(min(y, 0xFFFF), 0)
        if first:
            first_x, first_y = x, y
            first = False
        if move:
            con.dark(x, y, long=delay_dark, short=delay_dark)
            move = False
            continue
        con.light(x, y, long=delay_between, short=delay_between)
    if first_x is not None and first_y is not None:
        con.dark(first_x, first_y, long=delay_dark, short=delay_dark)
    con.light_off()
    con.write_port()
    con.v1_execute_light_list()


def _v1_convex_hull_points(ipts):
    """Convex hull (Andrew's monotone chain) on interpolated points.
    numpy-2-safe replacement for meerk40t's quickhull, which uses
    np.cross on 2D arrays (numpy 1.x only)."""
    pts = sorted(set((p.real, p.imag) for p in ipts if p is not None))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _v1_geomstr_hull(cls, geom, distance=50):
    """Replacement for Geomstr.hull - numpy 2 broke meerk40t's quickhull
    (np.cross on 2D arrays). This version computes the same hull with a
    numpy-2-safe monotone chain, so EVERY call site works: Live Hull,
    Trace Hull, and the console hull command."""
    ipts = list(geom.as_equal_interpolated_points(distance=distance))
    pts = _v1_convex_hull_points(ipts)
    if len(pts) < 3:
        return cls()
    pts = [complex(x, y) for x, y in pts]
    pts.append(pts[0])
    return Geomstr.lines(*pts)


def _v1_setup_listen(self, start):
    """Live-light listeners including element lifecycle signals.
    Upstream balormk gap (not V1-specific): balormk only listens to
    emphasis/edit signals - deleting an element fires 'element_removed'
    / 'tree_changed' which the light job missed, so deleted shapes kept
    being traced (stale simulation)."""
    if not self.listen:
        return
    methods = [
        "emphasized",
        "modified_by_tool",
        "updating",
        "view;realized",
        "update_group_labels",
        "element_property_reload",
        "element_removed",
        "tree_changed",
    ]
    for method in methods:
        if start:
            self.service.listen(method, self.on_emphasis_changed)
        else:
            self.service.unlisten(method, self.on_emphasis_changed)


def _v1_remove_nodes(self, node_list):
    """Replacement for Elemental.remove_nodes. Upstream MeerK40t bug
    (affects all users, not V1-specific): MeerK40t marks an element's
    reference nodes for deletion but never removes them (they live under
    the operations branch, not self.elems()). Deleted elements therefore
    stay in the operation's job - the 'shadow element' that keeps being
    simulated/engraved after deletion. This version removes the marked
    references too. (Reported upstream as meerk40t issue #3253.)"""
    self.set_start_time("remove_nodes")
    to_be_deleted = 0
    fastmode = False
    for node in node_list:
        for n in node.flat():
            n._mark_delete = True
            to_be_deleted += 1
            for ref in list(n._references):
                ref._mark_delete = True
                to_be_deleted += 1
    fastmode = to_be_deleted >= 100
    with self._node_lock:
        for n in reversed(list(self.elems())):
            if not hasattr(n, "_mark_delete"):
                continue
            if n.type in ("root", "branch elems", "branch reg", "branch ops"):
                continue
            n.remove_node(children=False, references=False, fast=fastmode)
        for op in list(self.ops()):
            for ref in list(op.flat()):
                if getattr(ref, "_mark_delete", False):
                    ref.remove_node(references=False, fast=fastmode)
    self.set_end_time("remove_nodes")
    if fastmode:
        self.signal("rebuild_tree", "all")
    else:
        self.signal("element_removed")


def _v1_copy_for_reinsertion(self):
    """V1: never re-run the light job after a real job. balormk stops
    the running light job when a real job starts and - with
    restart_light_jobs enabled - reinserts a copy, which then re-traces
    the selection (looks like an unprovoked re-run) and its stop can
    leave the board paused. The copy is inert instead."""
    c = _v1_copy_for_reinsertion.orig(self)
    c.stopped = True
    return c


def _v1_update_hull(self):
    """Hull tracing with numpy 2.x: meerk40t's quickhull implementation
    uses np.cross on 2D arrays (numpy 1.x only) and throws on numpy 2.
    Fall back to the selection's bounds box when the hull computation
    fails, so hull modes never crash."""

    def create_hull_geometry(elemlist):
        geometry = Geomstr()
        for node in elemlist:
            try:
                e = None
                if hasattr(node, "convex_hull"):
                    e = node.convex_hull()
                if e is None:
                    e = node.as_geometry()
            except AttributeError:
                continue
            geometry.append(e)
        if geometry.index == 0:
            return None
        try:
            return Geomstr.hull(geometry, distance=500)
        except Exception:
            bounds = Node.union_bounds(elemlist)
            if bounds is None or isinf(bounds[0]):
                return None
            xmin, ymin, xmax, ymax = bounds
            return Geomstr.lines(
                (xmin, ymin),
                (xmax, ymin),
                (xmax, ymax),
                (xmin, ymax),
                (xmin, ymin),
            )

    self._update_common(create_hull_geometry, "hull")


def patch():
    """Swap the balormk classes for the V1 versions (all import sites)."""
    mk_usb.USBConnection = V1MKConnection
    mk_ctrl.USBConnection = V1MKConnection
    mk_ctrl.GalvoController = V1MKController
    mk_driver.GalvoController = V1MKController
    import meerk40t.balormk.livelightjob as mk_light
    mk_light.LiveLightJob.trace_redlight = _v1_trace_redlight
    mk_light.LiveLightJob.update_hull = _v1_update_hull
    mk_light.LiveLightJob.setup_listen = _v1_setup_listen
    _v1_copy_for_reinsertion.orig = mk_light.LiveLightJob.copy_for_reinsertion
    mk_light.LiveLightJob.copy_for_reinsertion = _v1_copy_for_reinsertion
    from meerk40t.core.geomstr import Geomstr as _Geomstr
    _Geomstr.hull = classmethod(_v1_geomstr_hull)
    from meerk40t.core.elements.elements import Elemental as _Elemental
    _Elemental.remove_nodes = _v1_remove_nodes


patch()


if __name__ == "__main__":
    print("V1 MeerK40t profile loaded (balormk patched).")
