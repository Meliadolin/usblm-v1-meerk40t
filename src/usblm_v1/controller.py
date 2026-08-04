"""V1 controller: MeerK40t's balormk controller (GalvoController) with
V1 behavior on top - the init sequence, the buffered job model, the
state machine, and the recoveries, all hardware verified against a
real USBLM-V1 board (see docs/PROTOCOL.md).

The V1 board is a fiber driver board - the source is forced to "fiber"
even if the device was created as CO2/UV (they use wrong power records).
"""
import struct
import time

import meerk40t.balormk.controller as mk_ctrl

from .trace import trace
from .transport import RESP_EP, V1Connection  # noqa - pulls libusb bootstrap first

import usb.core  # noqa: E402 - must come after transport (libusb bootstrap)


class V1Controller(mk_ctrl.GalvoController):
    """V1 behavior on top of MeerK40t's balormk controller."""

    # The V1 board is a fiber driver board - force fiber source even if
    # the device was created as CO2/UV (they use wrong power records).
    @property
    def source(self):
        return "fiber"

    def connect_if_needed(self):
        """Same connect loop as balormk's GalvoController, but the
        transport is V1Connection (PID 9999, auto firmware upload from
        the loader PID 9990) instead of the stock USBConnection (which
        searches for the V2 board, PID 9899)."""
        if self._disable_connect:
            # After many failures automatic connects are disabled. We require a manual connection.
            self.abort_connect()
            self.connection = None
            raise ConnectionRefusedError(
                "LMC was unreachable. Explicit connect required."
            )
        if self.connection is None:
            if self.service.setting(bool, "mock", False) or self.force_mock:
                self.connection = mk_ctrl.MockConnection(
                    self.usb_log, device=self.service
                )
                name = self.service.safe_label
                self.connection.send = self.service.channel(f"{name}/send")
                self.connection.recv = self.service.channel(f"{name}/recv")
            else:
                self.connection = V1Connection(self.usb_log)
        self._is_opening = True
        self._abort_open = False
        count = 0
        while not self.connection.is_open(self._machine_index):
            try:
                if self.connection.open(self._machine_index) < 0:
                    raise ConnectionError
                self.init_laser()
            except (ConnectionError, ConnectionRefusedError):
                if count == 0:
                    self.service("clone_init\n")
                time.sleep(0.3)
                count += 1
                if self.is_shutdown or self._abort_open:
                    self._is_opening = False
                    self._abort_open = False
                    return
                if self.connection.is_open(self._machine_index):
                    self.connection.close(self._machine_index)
                if count >= 10:
                    # We have failed too many times.
                    self._is_opening = False
                    self.set_disable_connect(True)
                    self.usb_log("Could not connect to the LMC controller.")
                    self.usb_log("Automatic connections disabled.")
                    from platform import system

                    osname = system()
                    if osname == "Windows":
                        self.usb_log(
                            "Did you install the libusb driver via Zadig (https://zadig.akeo.ie/)?"
                        )
                        self.usb_log(
                            "Consult the wiki: https://github.com/meerk40t/meerk40t/wiki/Install%3A-Windows"
                        )
                    raise ConnectionRefusedError(
                        "Could not connect to the LMC controller."
                    )
                time.sleep(0.3)
                continue
        self._is_opening = False
        self._abort_open = False

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
        trace("status: FAIL - no valid poll response after 6 tries")
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
                trace("_list_end: board not ready (buffer full) - "
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
        trace("_flush_batch: batch executed and cleared")

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
                trace("wait_ready: TIMEOUT after 5s")
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
            trace("_cpu_reset: CPUCS toggle (0xE600)")
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x01", timeout=500)
            time.sleep(0.1)
            dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b"\x00", timeout=500)
        except Exception as e:
            trace(f"_cpu_reset FAILED: {e}")

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
                trace("wait_idle: GLOBAL TIMEOUT after 10 min")
                return
            st = self.status()
            if st in RUNNING:
                stuck_t0 = None
                continue
            if stuck_t0 is None:
                stuck_t0 = time.time()
            elif time.time() - stuck_t0 > 2.0:
                trace(f"wait_idle: stuck at {hex(st) if st else 'None'} "
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
                trace(f"wait_idle: still stuck at "
                      f"{hex(st2) if st2 else 'None'} - CPUCS reboot")
                self._cpu_reset()
                time.sleep(0.8)
                try:
                    self.init_laser()     # re-init after firmware reboot
                except Exception as e:
                    trace(f"wait_idle: re-init failed: {e}")
                return

    def init_laser(self):
        """V1 verified EZCAD 2.5.3 init (balormk's sends 0x0040 Reset +
        serial query which the V1 board does not use)."""
        trace("init_laser: start (V1 EZCAD 2.5.3 sequence)")
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
        trace("init_laser: done")

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
            trace(f"rapid_mode: executing list ({self._number_of_list_packets} packet(s))")
            self._clear_pause()
            self.execute_list()
            self._command(0x0016, 1)      # SetControlMode(1)
        self._list_executing = False
        self._number_of_list_packets = 0
        self.wait_idle()
        st = self.status()
        trace(f"rapid_mode: idle, state={hex(st) if st is not None else 'None'}")
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
            trace(f"_clear_pause: state {hex(st)} - StopExecute")
            self._command(0x001F)

    def write_correction_file(self, filename):
        """V1: the 0x0015 cor-table payload format is undecoded - refuse
        instead of sending garbage to the board."""
        trace("write_correction_file: not supported on V1 (0x0015 payload unknown)")
        self.usb_log("Correction file upload is not supported on the V1 board.")
        return None

    def write_blank_correct_file(self):
        trace("write_blank_correct_file: not supported on V1")
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
        trace(f"light pass: executing {self._number_of_list_packets} packet(s)")
        self._clear_pause()
        self.execute_list()
        self._command(0x0016, 1)
        self._list_executing = True
        t0 = time.time()
        while self.is_busy():
            time.sleep(0.02)
            if time.time() - t0 > 10.0:
                trace("light pass: idle wait TIMEOUT after 10s")
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
            trace("program_mode: V1 transition (0x0009, 0x0034, ...)")
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
