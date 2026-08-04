#!/usr/bin/env python3
"""INTERIM shim for the USBLM-V1 profile restructure (Phase 1).

Re-exports the usblm_v1 package classes under the old names and applies
the temporary class swap. Deleted when the profile becomes a proper
MeerK40t device (Phase 2) - kept so the existing test suite keeps
running unchanged during the transition.

Usage:
    import v1_meerk40t   # BEFORE starting the GUI / creating the device
"""
import usblm_v1  # noqa: F401 - applies the bundled upstream fixes
from usblm_v1.legacy_patch import patch
from usblm_v1.controller import V1Controller as V1MKController
from usblm_v1.transport import V1Connection as V1MKConnection
from usblm_v1.transport import scan_windows_usb as _scan_windows_usb

__version__ = "1.1.0"

patch()


if __name__ == "__main__":
    print("V1 MeerK40t profile loaded (balormk patched).")
