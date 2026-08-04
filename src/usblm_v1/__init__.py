"""USBLM-V1 device profile for MeerK40t.

Makes the free cross-platform GUI laser software drive the BJJCZ USBLM-V1
board (VID 9588 / PID 9999) as its own device in MeerK40t's device list -
MeerK40t's balormk plugin is left untouched.

Wire model (hardware verified, see docs/PROTOCOL.md):
  V1 command : 14B = [0x0002, code, p1..p5] on EP 0x01
  V1 poll    :  2B = [0x0001]                on EP 0x01
  V1 list    : 3072B chunks                  on EP 0x02
  V1 response: 10B = 5 words LE              on EP 0x81 (return first 8)
  V1 status  : poll w[3] = state; 0x0220 idle / 0x0224 running
  V1 chunks  : every chunk write gets a 0x0003 progress ACK on EP 0x81
               - must be drained or all later reads desync
  V1 lists   : buffer all chunks, ExecuteList (0x0005) once at the end

The profile bundles fixes for two upstream MeerK40t bugs (numpy-2
Geomstr.hull, Elemental.remove_nodes issue #3253) - applied on import.
"""
from . import upstream_patches  # noqa: F401

__version__ = "1.1.0"

upstream_patches.apply_upstream_patches()
