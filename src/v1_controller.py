#!/usr/bin/env python3
"""
BJJCZ USBLM-V1 Laser Controller - Native 64-bit
Protocol reverse-engineered from USBPcap capture of EZCAD 2.5.3
(see docs/PROTOCOL.md)

ENDPOINTS (iface 0):
  EP 0x01 OUT = command channel
  EP 0x81 IN  = response channel (10-byte = 5 words LE)
  EP 0x02 OUT = segment stream channel (3072B chunks = 256 x 12B records)

COMMAND: 14 bytes = 7 words LE: [0x0002, code, p1..p5]
RESPONSE: 10 bytes = 5 words LE: [echo..., status]

SEGMENT RECORD: 12 bytes = 6 words LE: [opcode, x, y, mark, dist, 0]
  opcode: 0x8001 jump (laser off), 0x8005 mark (laser on)
  mark:   0x8000 for mark segments, 0 for jumps
  dist:   euclidean distance from previous point (board uses it for timing)
"""

import math
import os
import struct
import sys
import time

__version__ = "1.1.0"

import libusb_bootstrap  # noqa: F401 - must be before usb.core
import usb.core
import usb.util

VID = 0x9588
PID = 0x9999
CMD_EP = 0x01      # EP 0x01 OUT
RESP_EP = 0x81     # EP 0x81 IN
DATA_EP = 0x02     # EP 0x02 OUT (segment stream)
CHUNK_SIZE = 3072  # 256 records x 12 bytes


class V1Controller:
    def __init__(self):
        self._dev = None
        self._connected = False

    # ---------------- low level ----------------

    def connect(self):
        if self._connected:
            return
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if not dev:
            # try loader: upload firmware, then find again
            dev = usb.core.find(idVendor=VID, idProduct=0x9990)
            if dev:
                print("Board in loader mode - uploading firmware...")
                import upload_firmware
                upload_firmware.upload()
                dev = usb.core.find(idVendor=VID, idProduct=PID)
            if not dev:
                raise RuntimeError("V1 board not found! Is it plugged in?")
        try:
            dev.set_configuration()
            dev.set_interface_altsetting(0, 0)
            usb.util.claim_interface(dev, 0)
        except usb.core.USBError as e:
            print(f"claim failed ({e}) - trying CPUCS reset...")
            try:
                dev.set_configuration()
                usb.util.claim_interface(dev, 0)
                dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b'\x01', timeout=500)
                time.sleep(0.05)
                dev.ctrl_transfer(0x40, 0xA0, 0xE600, 0, b'\x00', timeout=500)
                time.sleep(0.3)
                usb.util.release_interface(dev, 0)
            except usb.core.USBError:
                pass
            dev.set_configuration()
            dev.set_interface_altsetting(0, 0)
            usb.util.claim_interface(dev, 0)
        self._dev = dev
        self._connected = True
        print(f"Connected V1 board (bus={dev.bus}, addr={dev.address})")

    def disconnect(self):
        if self._connected:
            try:
                usb.util.release_interface(self._dev, 0)
            except Exception:
                pass
            self._connected = False

    def _flush(self):
        for _ in range(5):
            try:
                self._dev.read(RESP_EP, 64, timeout=10)
            except usb.core.USBTimeoutError:
                break

    def _cmd(self, code, *params, wait=0.005):
        """Send 14-byte command on EP0x01, return 10-byte response (5 words)"""
        p = list(params) + [0] * 5
        pkt = struct.pack('<7H', 0x0002, code, *p[:5])
        self._flush()
        self._dev.write(CMD_EP, pkt, timeout=500)
        time.sleep(wait)
        for delay in [0.002, 0.005, 0.010, 0.020, 0.050]:
            time.sleep(delay)
            try:
                r = bytes(self._dev.read(RESP_EP, 64, timeout=200))
                if r:
                    return struct.unpack('<5H', r[:10])
            except usb.core.USBTimeoutError:
                continue
        return None

    def _poll(self):
        """01 00 - status poll. Returns (last_cmd, state, flag) or None"""
        pkt = struct.pack('<H', 0x0001)
        try:
            self._dev.write(CMD_EP, pkt, timeout=200)
        except usb.core.USBTimeoutError:
            return None
        time.sleep(0.002)
        try:
            r = bytes(self._dev.read(RESP_EP, 64, timeout=200))
            if len(r) >= 10:
                w = struct.unpack('<5H', r[:10])
                return (w[1], w[3], w[4])
        except usb.core.USBTimeoutError:
            pass
        return None

    def _progress(self):
        """03 00 - progress poll while a list runs. Returns position counter"""
        pkt = struct.pack('<H', 0x0003)
        try:
            self._dev.write(CMD_EP, pkt, timeout=200)
        except usb.core.USBTimeoutError:
            return None
        time.sleep(0.002)
        try:
            r = bytes(self._dev.read(RESP_EP, 64, timeout=200))
            if len(r) >= 10:
                w = struct.unpack('<5H', r[:10])
                return w[3]
        except usb.core.USBTimeoutError:
            pass
        return None

    # ---------------- segments ----------------

    @staticmethod
    def _seg(opcode, x, y, mark, dist):
        return struct.pack('<6H', opcode, x & 0xFFFF, y & 0xFFFF, mark, dist, 0)

    def _build_chunk(self, records, pad_to=CHUNK_SIZE):
        """Pad records to pad_to bytes (default 3072). pad_to=0 = no padding"""
        n = len(records)
        chunk = b''.join(records)
        if pad_to:
            chunk += b'\x00' * (pad_to - len(chunk))
        return chunk

    def _dist(self, x0, y0, x, y):
        return int(round(math.hypot(x - x0, y - y0)))

    def outline(self, points, speed_units=2516, x0=None, y0=None, duration=None, pad_to=0, stop=False):
        """Walk the outline (laser off) through the given points.
        points: list of (x, y) 0-65535. Matches EZCAD 0x8001 jumps.
        pad_to=0 -> stream only the real records (continuous looping)."""
        records = []
        px, py = (x0, y0) if x0 is not None else (0x8000, 0x8000)
        for (x, y) in points:
            records.append(self._seg(0x8001, x, y, 0, self._dist(px, py, x, y)))
            px, py = x, y
        self._run(records, duration=duration, pad_to=pad_to, stop=stop)

    def mark(self, points, mark_speed=0x0320, power=0x0FFF, freq=0x03E8,
             duration=None, stop=False):
        """Mark the outline (laser on) through the given points.
        points: list of (x, y). Uses the verified buffered-job engine."""
        segs = []
        px, py = points[0]
        for (x, y) in points[1:]:
            segs.append((px, py, x, y))
            px, py = x, y
        self.mark_job(segs, mark_speed=mark_speed, power=power, freq=freq,
                      duration=duration, stop=stop)

    def fill(self, x0, y0, x1, y1, step=0x200, mark_speed=0x0320,
             power=0x0FFF, freq=0x03E8, duration=None, stop=False):
        """Fill rectangle (x0,y0)-(x1,y1) with horizontal lines (laser on).
        step = line spacing in units (default 0x200 = 512)."""
        segs = []
        y = y0
        row = 0
        while y <= y1:
            if row % 2 == 0:
                segs.append((x0, y, x1, y))
            else:
                segs.append((x1, y, x0, y))
            y += step
            row += 1
        self.mark_job(segs, mark_speed=mark_speed, power=power, freq=freq,
                      duration=duration, stop=stop)

    def _run_chunk(self, chunk, duration=None, stop=False, laser=False):
        """Execute a pre-built 3072B chunk (or list of chunks) with the
        VERIFIED EZCAD buffered-job sequence:
          1. transition: 0x0009, 0x0034, poll, 0x0012, 0x000C,
             0x000D(0x8001,0x8001), [laser: 0x0033(1) MO open], poll, poll
          2. queue chunk(s) with poll-pair between
          3. 0x0005 ExecuteList, 0x0016(1)
          4. poll fast until state 0x0220 (idle)
          5. goto center
        The board buffers the whole job - do NOT re-send chunks during
        execution (overwrites buffer, only last chunk runs)."""
        if isinstance(chunk, (list, tuple)):
            chunks = list(chunk)
        else:
            chunks = [chunk]

        # transition (verified first-run sequence)
        self._try_cmd(0x0009)
        self._try_cmd(0x0034)
        self._poll()
        self._try_cmd(0x0012)
        self._try_cmd(0x000C)
        self._try_cmd(0x000D, 0x8001, 0x8001)
        if laser:
            self._try_cmd(0x0033, 0x0001)   # Fiber_SetMo = 1 OPEN
        self._poll()
        self._progress()

        # queue all chunks with poll-pair between (verified pattern)
        for i, ch in enumerate(chunks):
            self._dev.write(DATA_EP, ch, timeout=500)
            if i < len(chunks) - 1:
                self._poll()
                self._progress()
        self._try_cmd(0x0005)               # ExecuteList
        self._try_cmd(0x0016, 0x0001)

        # poll fast until idle (0x0220) - verified completion signal
        if duration is None:
            total = 0
            for ch in chunks:
                for i in range(0, len(ch) - 11, 12):
                    w = struct.unpack_from('<6H', ch, i)
                    if w[0] in (0x8001, 0x8005):
                        total += w[4]
            duration = total / (0x0320 * 778.0) + 5.0   # mark speed 800
        print(f"  run {len(chunks)} chunk(s), est {duration:.1f}s")

        t0 = time.time()
        i = 0
        while time.time() - t0 < duration:
            st = self._poll_100()
            i += 1
            if st is not None and st[1] == 0x0220:
                print(f"  IDLE after {time.time()-t0:.2f}s ({i} polls)")
                break
            time.sleep(0.005)
        else:
            print(f"  TIMEOUT after {time.time()-t0:.0f}s ({i} polls)")

        # return galvo to center (like EZCAD)
        self._try_cmd(0x000D, 0x8000, 0x8000)
        time.sleep(0.2)

        # optional end-of-session sequence
        if stop:
            for code, args in [(0x0012, ()), (0x0033, (1,)), (0x0016, (1,)),
                               (0x0021, (0,)), (0x001D, (2000, 20, 1)),
                               (0x0033, ())]:
                for attempt in range(3):
                    r = self._try_cmd(code, *args)
                    if r is not None:
                        break
                    time.sleep(0.05)

    def mark_job(self, segments, mark_speed=0x0320, power=0x0FFF,
                 freq=0x03E8, duration=None, stop=False, home=True):
        """CORE ENGINE for marking software. Takes a flat list of segments
        [(sx,sy,ex,ey), ...], builds ONE job (settings + jumps + marks),
        splits into 3072B chunks, executes, waits for idle.

        segments: list of (sx, sy, ex, ey) - jump then mark each.
        mark_speed: 0x800C record value (800 -> ~624k u/s)
        power: 0x8012 record value (0x0FFF = max)
        freq: 0x801B record value (1000)
        stop: True sends EZCAD end-of-session sequence after.
        home: True returns galvo to center when done."""
        settings = [
            self._seg(0x8051, 0, 0, 0, 0),          # listReadyMark
            self._seg(0x8004, 0x0320, 0, 0, 0),     # open-MO delay
            self._seg(0x8011, 0x0001, 0, 0, 0),     # listWritePort
            self._seg(0x8004, 0x01F4, 0, 0, 0),     # mark delay
            self._seg(0x801B, freq, 0, 0, 0),       # Q-switch freq
            self._seg(0x8012, power, 0, 0, 0),      # POWER
            self._seg(0x8006, 0x0D1B, 0, 0, 0),     # jump speed
            self._seg(0x800C, mark_speed, 0, 0, 0), # mark speed
            self._seg(0x8007, 0x012C, 0, 0, 0),
            self._seg(0x8008, 0x0064, 0, 0, 0),
            self._seg(0x800F, 0x000A, 0, 0, 0),
            self._seg(0x800D, 0x0199, 0, 0, 0),
        ]
        records = list(settings)
        px, py = 0x8000, 0x8000
        first = True
        for (sx, sy, ex, ey) in segments:
            d = self._dist(px, py, sx, sy)
            records.append(self._seg(0x8001, sx, sy, 0, d))
            px, py = sx, sy
            d = self._dist(px, py, ex, ey)
            flag = 0 if first else 0x8000
            records.append(self._seg(0x8005, ex, ey, flag, d))
            px, py = ex, ey
            first = False
        chunks = []
        per = 256
        for i in range(0, len(records), per):
            part = records[i:i+per]
            body = b''.join(part)
            n_pad = (CHUNK_SIZE - len(body)) // 12
            body += self._seg(0x8002, 0, 0, 0, 0) * n_pad
            chunks.append(body)
        self._run_chunk(chunks, duration=duration, stop=stop, laser=True)
        return chunks

    def _poll_100(self):
        """01 00 status poll with 100ms timeouts (stream-loop version)."""
        try:
            self._dev.write(CMD_EP, struct.pack('<H', 0x0001), timeout=100)
        except usb.core.USBTimeoutError:
            return None
        try:
            r = bytes(self._dev.read(RESP_EP, 64, timeout=100))
            if len(r) >= 10:
                w = struct.unpack('<5H', r[:10])
                return (w[1], w[3], w[4])
        except usb.core.USBTimeoutError:
            pass
        return None

    def _progress_100(self):
        """03 00 progress poll with 100ms timeouts (stream-loop version)."""
        try:
            self._dev.write(CMD_EP, struct.pack('<H', 0x0003), timeout=100)
        except usb.core.USBTimeoutError:
            return None
        try:
            r = bytes(self._dev.read(RESP_EP, 64, timeout=100))
            if len(r) >= 10:
                return struct.unpack('<5H', r[:10])[3]
        except usb.core.USBTimeoutError:
            pass
        return None

    def _recover_idle(self):
        """Poll until the board reports idle (0x0220). If it stays busy,
        send the stop sequence to force it back to idle."""
        t0 = time.time()
        while time.time() - t0 < 3.0:
            st = self._poll()
            if st is not None and st[1] == 0x0220:
                return True
            time.sleep(0.05)
        # still busy - force stop (EZCAD inter-run: 0x0021(0), 0x001D standby)
        for code, args in [(0x0021, (0,)), (0x001D, (2000, 20, 1)),
                           (0x0034, ()), (0x0012, ()),
                           (0x0033, (1,)), (0x0016, (1,))]:
            self._try_cmd(code, *args)
            time.sleep(0.05)
        time.sleep(0.3)
        return False

    def _run(self, records, duration=None, pad_to=CHUNK_SIZE, stop=False,
             settings=None):
        """Download chunk to EP0x02 and run the list (EZCAD sequence).
        The board executes records in REAL-TIME from the EP0x02 pipe -
        EZCAD re-sends the same 3072B chunk on every poll cycle (~16ms)
        until the run ends. The board LOOPS the list while the host
        streams, so the run is time-limited (like EZCAD does).
        stop=True: send the end-of-session stop sequence (only at the
        very end, matching EZCAD - it does NOT stop between runs)."""
        if settings is None:
            # outline settings (from capture)
            settings = b''.join([
                self._seg(0x8006, 2516, 0, 0, 0),
                self._seg(0x800C, 2516, 0, 0, 0),
                self._seg(0x8007, 0, 0, 0, 0),
                self._seg(0x8008, 0, 0, 0, 0),
                self._seg(0x800F, 0, 0, 0, 0),
                self._seg(0x800D, 0, 0, 0, 0),
            ])
        data_chunk = self._build_chunk(records, pad_to=pad_to)
        settings_chunk = settings + b'\x00' * (CHUNK_SIZE - len(settings))

        # exact EZCAD transition: 0x001F, 0x0033, 0x0021(4), 0x0021(0),
        # poll, 0x0009, 0x0034, poll, 0x0012, 0x000C, 0x000D(pos), 0x0033(1)
        self._try_cmd(0x001F)               # download start
        self._try_cmd(0x0033)
        self._try_cmd(0x0021, 0x0004)       # start list
        self._try_cmd(0x0021, 0x0000)       # stop/clear
        self._poll()
        self._try_cmd(0x0009)               # reset
        self._try_cmd(0x0034)
        self._poll()
        self._try_cmd(0x0012)               # reset motion
        self._try_cmd(0x000C)
        self._try_cmd(0x000D, 0x8001, 0x8001)  # move to home corner
        self._try_cmd(0x0033, 0x0001)
        self._poll()
        self._progress()

        # settings chunk first
        self._write_chunk(settings_chunk, "settings")
        self._poll()
        self._progress()
        # then segment chunk
        self._write_chunk(data_chunk, "segments")
        self._try_cmd(0x0005)               # START EXECUTION (laser per records)
        self._try_cmd(0x0016, 0x0001)       # control mode

        # time-limit: estimate from total distance / speed. EZCAD uses a
        # computed duration; the board loops while streaming.
        if duration is None:
            total_dist = 0
            for r in records:
                total_dist += struct.unpack_from('<H', r, 8)[0]  # word4 = distance
            # speed param 2516 -> ~23800 units/s observed in capture
            duration = max(1.5, total_dist / 23800.0 + 0.4)
        print(f"  run: {len(records)} records, streaming {duration:.1f}s")

        # poll loop: status + progress + re-send data chunk (like EZCAD).
        t_loop = time.time()
        i = 0
        while time.time() - t_loop < duration:
            self._poll()
            self._progress()
            self._write_chunk(data_chunk, "stream", timeout=100)
            i += 1
            time.sleep(0.005)
        print(f"  run loop: {i} cycles, {time.time()-t_loop:.2f}s")

        # optional end-of-session stop - tolerant, only when stop=True
        if stop:
            for code, args in [(0x0021, (0,)), (0x0034, ()), (0x0012, ()),
                               (0x0033, (1,)), (0x0016, (1,))]:
                for attempt in range(5):
                    r = self._try_cmd(code, *args)
                    if r is not None:
                        break
                    time.sleep(0.05)

    def _try_cmd(self, code, *params, wait=0.005):
        """Like _cmd but never raises on write timeout."""
        p = list(params) + [0] * 5
        pkt = struct.pack('<7H', 0x0002, code, *p[:5])
        try:
            self._dev.write(CMD_EP, pkt, timeout=300)
        except usb.core.USBTimeoutError:
            return None
        time.sleep(wait)
        for delay in [0.002, 0.005, 0.010, 0.020]:
            time.sleep(delay)
            try:
                r = bytes(self._dev.read(RESP_EP, 64, timeout=200))
                if r:
                    return struct.unpack('<5H', r[:10])
            except usb.core.USBTimeoutError:
                continue
        return None

    def _write_chunk(self, chunk, tag, timeout=200):
        """Write 3072B chunk to EP0x02. The board drains it during execution;
        tolerate timeouts (board busy) - it reads what it can."""
        try:
            self._dev.write(DATA_EP, chunk, timeout=timeout)
            return True
        except usb.core.USBTimeoutError:
            return False

    # ---------------- init (exact EZCAD sequence) ----------------

    def init(self):
        print("Initializing V1 board (EZCAD 2.5.3 sequence)...")
        self._cmd(0x0009)
        v = self._cmd(0x0007, 1)
        if v:
            print(f"  Version: 0x{v[3]:04X}")
        self._cmd(0x0003, wait=0)  # 4-byte variant handled below
        # 04 00 03 00 is a 4-byte command: word0=0x0004, word1=0x0003
        self._flush()
        self._dev.write(CMD_EP, struct.pack('<2H', 0x0004, 0x0003), timeout=500)
        time.sleep(0.005)
        try:
            self._dev.read(RESP_EP, 64, timeout=200)
        except usb.core.USBTimeoutError:
            pass
        self._cmd(0x0007, 1)
        self._cmd(0x0015)
        self._cmd(0x0004)
        self._cmd(0x0016, 0)
        self._cmd(0x001B, 1)
        self._cmd(0x0017, 1)
        self._cmd(0x001C, 1)
        self._cmd(0x001D, 2000, 20, 1)
        self._cmd(0x001A, 200)
        self._cmd(0x001E, 50)
        self._cmd(0x0006, 50)
        self._cmd(0x0033)
        self._poll()
        self._cmd(0x0062, 0x0FFB, 1, 0x0199, 100)
        self._cmd(0x0007, 1)
        self._flush()
        self._dev.write(CMD_EP, struct.pack('<7H', 0x0006, 0x0032, 0, 0x00A3, 0x03E8, 0x0019, 0), timeout=500)
        time.sleep(0.005)
        try:
            self._dev.read(RESP_EP, 64, timeout=200)
        except usb.core.USBTimeoutError:
            pass
        self._cmd(0x0021, 0)
        self._cmd(0x003A)
        print("  Initialized!")

    # ---------------- helpers ----------------

    def goto(self, x, y):
        """Jump to position (0-65535)"""
        self._cmd(0x000D, x, y)

    def mark_square(self, size=17235, x0=0x724E, y0=0x48A8):
        """Mirror of the captured EZCAD test: rectangle w=17235 h=23223"""
        cx, cy = x0, y0
        self.outline([(cx, cy + size), (cx + size, cy + size),
                      (cx + size, cy), (cx, cy)])
        time.sleep(0.2)
        self.mark([(cx, cy + size), (cx + size, cy + size),
                   (cx + size, cy), (cx, cy)])
        print("Rectangle outlined + marked")


if __name__ == "__main__":
    print("=" * 50)
    print("  BJJCZ USBLM-V1 Laser Controller (64-bit)")
    print("=" * 50)
    ctrl = V1Controller()
    try:
        ctrl.connect()
        ctrl.init()
        print("\nBoard ready! Try:")
        print("  ctrl.outline([(0x6000,0x6000),(0xA000,0x6000),(0xA000,0xA000),(0x6000,0xA000)])")
        print("  ctrl.mark([...same points...])")
        print("  ctrl.goto(0x8000, 0x8000)   - center")
    finally:
        ctrl.disconnect()
