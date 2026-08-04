"""V1 USB transport: dispatch commands/polls/chunks to the right
endpoints, read 10-byte responses, return the first 8 bytes MeerK40t
expects. Subclasses balormk's USBConnection for the connection plumbing
(claim/detach/config) and overrides everything wire-specific.

The V1 board drops into loader mode (PID 9990) on a USB bus reset -
balormk's close() resets by default, so the V1 transport never does.
The firmware survives; loader mode just needs a re-upload.
"""
import re
import subprocess
import time

from usblm_v1 import bootstrap  # noqa: F401 - MUST be before usb.core

import usb.core
import usb.util

import meerk40t.balormk.usb_connection as mk_usb

from .trace import trace

VID_V1 = 0x9588
PID_V1 = 0x9999
PID_V1_LOADER = 0x9990
CMD_EP = 0x01
RESP_EP = 0x81
DATA_EP = 0x02

IDLE_STATE = 0x0220


def scan_windows_usb():
    """Windows-side check for the board. libusb's WinUSB backend cannot
    see a device that has NO driver bound - this scans the Windows
    device tree via pnputil and reports the real state."""
    try:
        out = subprocess.run(["pnputil", "/enum-devices"],
                             capture_output=True, text=True, timeout=30)
        text = out.stdout
    except Exception as e:
        trace(f"scan_windows_usb: pnputil failed: {e}")
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
            trace(msg)
            if not driver:
                print("  FIX: install the WinUSB driver - run scripts\\bind_winusb.cmd "
                      "(or SetupPanel button 2)")
                trace("  FIX: install the WinUSB driver - run scripts\\bind_winusb.cmd")


class V1Connection(mk_usb.USBConnection):
    """V1 transport: dispatch commands/polls/chunks to the right endpoints,
    read 10-byte responses, return the first 8 bytes MeerK40t expects."""

    def find_device(self, index=0):
        self.channel("Using LibUSB to connect (V1 profile).")
        trace("find_device: searching PID 9999")
        dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            loader = usb.core.find(idVendor=VID_V1, idProduct=PID_V1_LOADER)
            if loader is not None:
                self.channel("Board in loader mode - uploading firmware...")
                trace("find_device: loader mode (9990) - uploading firmware")
                import upload_firmware
                upload_firmware.upload()
                time.sleep(1.0)
                trace("find_device: waiting for re-enumeration")
                dev = usb.core.find(idVendor=VID_V1, idProduct=PID_V1)
        if dev is None:
            self.channel("V1 board not found (need PID 9999).")
            trace("find_device: FAIL - board not found via libusb")
            scan_windows_usb()
            raise ConnectionRefusedError
        self.devices[index] = dev
        trace(f"find_device: OK bus={dev.bus} addr={dev.address}")
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
