#!/usr/bin/env python3
"""
BJJCZ V1 firmware uploader - replays the exact LMCUSB.sys loader sequence
extracted from the Win7 USBPcap capture (v1_upload_sequence.dat).

Loader: PID_9990, standard Cypress FX2LP vendor protocol:
  ctrl_transfer(0x40, 0xA0, addr, 0, data)
Sequence (from capture):
  0xE600=0x01  -> halt CPU (CPUCS)
  ... firmware chunks at 0x0000-0x1FFF ...
  0x14C9=0x00  -> (timer/param)
  0xE600=0x00  -> start CPU, board re-enumerates as PID_9999
"""
import os
import struct
import sys
import time

__version__ = "1.1.0"

import libusb_bootstrap  # noqa: F401 - must be before usb.core
import usb.core
import usb.util

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)   # next to the .exe
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)  # extracted onefile bundle
    ROOT = APP_DIR
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEQ = None
for _cand in (
    os.path.join(BUNDLE_DIR, "data", "v1_upload_sequence.dat"),  # frozen
    os.path.join(os.path.dirname(BUNDLE_DIR), "data",            # repo layout
                 "v1_upload_sequence.dat"),
    os.path.join(APP_DIR, "data", "v1_upload_sequence.dat"),     # module-adjacent
):
    if os.path.exists(_cand):
        SEQ = _cand
        break
if SEQ is None:
    SEQ = os.path.join(BUNDLE_DIR, "data", "v1_upload_sequence.dat")
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "upload_log.txt")


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def load_sequence(path=SEQ):
    with open(path, "rb") as f:
        n = struct.unpack('<I', f.read(4))[0]
        writes = []
        for _ in range(n):
            addr, wlen = struct.unpack('<HH', f.read(4))
            body = f.read(wlen)
            writes.append((addr, body))
    return writes

def find_loader():
    return usb.core.find(idVendor=0x9588, idProduct=0x9990)

def upload(path=SEQ):
    _log(f"upload: start ({os.path.basename(path)})")
    writes = load_sequence(path)
    dev = find_loader()
    if not dev:
        _log("upload: FAIL - no loader found")
        print("No loader (PID_9990) found. Board may be in normal mode (9999).")
        return False
    _log(f"upload: loader found bus={dev.bus} addr={dev.address}, {len(writes)} writes")
    print(f"Loader found: bus={dev.bus} addr={dev.address}, {len(writes)} writes to replay")
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass
    usb.util.claim_interface(dev, 0)

    t0 = time.time()
    ok = 0
    for i, (addr, body) in enumerate(writes):
        try:
            dev.ctrl_transfer(0x40, 0xA0, addr, 0, body, timeout=500)
            ok += 1
        except usb.core.USBError as e:
            _log(f"upload: FAIL at write {i} addr={addr:04X}: {e}")
            print(f"WRITE FAILED at {i}: addr={addr:04X} len={len(body)}: {e}")
            usb.util.release_interface(dev, 0)
            return False
    _log(f"upload: replayed {ok}/{len(writes)} in {time.time()-t0:.2f}s")
    print(f"Replayed {ok}/{len(writes)} writes in {time.time()-t0:.2f}s")
    usb.util.release_interface(dev, 0)

    print("Waiting for re-enumeration as PID_9999...")
    for _ in range(20):
        time.sleep(0.5)
        d9 = usb.core.find(idVendor=0x9588, idProduct=0x9999)
        if d9:
            _log("upload: SUCCESS - board re-enumerated as PID_9999")
            print(f"SUCCESS: board is now PID_9999 (bus={d9.bus} addr={d9.address})")
            return True
    _log("upload: FAIL - board did not re-enumerate")
    print("Board did not re-enumerate as 9999.")
    return False

if __name__ == "__main__":
    if "--version" in sys.argv:
        print(f"upload_firmware {__version__}")
        sys.exit(0)
    upload()
