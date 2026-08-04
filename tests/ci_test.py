#!/usr/bin/env python3
"""Offline CI test - no board required. Run by GitHub Actions after a build.

Asserts: every src module imports, version strings are present, the
firmware upload sequence parses and starts/ends the way the board expects,
the list-record chunk layout is byte-exact, the USBLM-V1 device
provider registers with a bare kernel, and the offline galvoplotter
mock flow still passes. Exits nonzero on the first failing group.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
sys.path.insert(0, SRC)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  [PASS] {name}")
    else:
        FAILURES.append(name)
        print(f"  [FAIL] {name} {detail}")


def main():
    print("=== usblm-v1-meerk40t offline CI test ===\n")

    # 1. imports + versions
    import libusb_bootstrap  # noqa: F401
    import v1_controller
    import v1_galvoplotter
    import usblm_v1
    import upload_firmware
    check("all src modules import", True)
    for mod in (v1_controller, v1_galvoplotter, usblm_v1, upload_firmware):
        check(f"{mod.__name__} has __version__", getattr(mod, "__version__", None) == "1.1.0")

    # 2. firmware upload sequence parses + is the known-good shape
    seq_path = os.path.join(os.path.dirname(SRC), "data",
                            "v1_upload_sequence.dat")
    writes = upload_firmware.load_sequence(seq_path)
    check("firmware sequence parses", len(writes) > 400, f"n={len(writes)}")
    check("sequence starts with CPU halt (0xE600=1)",
          writes[0][0] == 0xE600 and writes[0][1] == b"\x01",
          f"first={writes[0]}")
    check("sequence ends with CPU start (0xE600=0)",
          writes[-1][0] == 0xE600 and writes[-1][1] == b"\x00",
          f"last={writes[-1]}")
    check("all writes are sane (addr <= 0xFFFF, len <= 4096)",
          all(a <= 0xFFFF and 0 < len(b) <= 4096 for a, b in writes))

    # 3. list-record chunk layout is byte-exact
    rec = v1_controller.V1Controller._seg(0x8005, 0x1234, 0x5678, 0x8000, 100)
    check("mark record is 12 bytes", len(rec) == 12)
    check("mark record words are LE [op,x,y,mark,dist,0]",
          struct.unpack("<6H", rec) == (0x8005, 0x1234, 0x5678, 0x8000, 100, 0))
    chunk = v1_controller.V1Controller()._build_chunk([rec])
    check("chunk is exactly 3072 bytes", len(chunk) == 3072)
    check("chunk pads with zeroes", chunk[3072 - 12:] == b"\x00" * 12)
    recs = [v1_controller.V1Controller._seg(0x8001, x, x, 0, 0)
            for x in range(0x1000, 0x1100)]
    chunk = v1_controller.V1Controller()._build_chunk(recs)
    check("256 records fit one chunk", len(chunk) == 3072)

    # 4. offline galvoplotter flow (fake board transport)
    r_mock = subprocess.run(
        [sys.executable, os.path.join(HERE, "test_v1_galvoplotter_mock.py")],
        capture_output=True, text=True)
    check("galvoplotter offline mock passes", r_mock.returncode == 0,
          (r_mock.stderr or r_mock.stdout)[:200])

    # 5. device-provider registration (needs meerk40t installed)
    r_reg = subprocess.run(
        [sys.executable, os.path.join(HERE, "test_registration.py")],
        capture_output=True, text=True)
    check("device-provider registration passes", r_reg.returncode == 0,
          (r_reg.stderr or r_reg.stdout)[:200])

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} checks: {', '.join(FAILURES)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
