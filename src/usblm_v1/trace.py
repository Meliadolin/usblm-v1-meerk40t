"""Progress tracing: logs\\v1_shim_trace.log in the package root
(next to the exe when frozen, else three levels up from this file)."""
import os
import sys
import time

if getattr(sys, "frozen", False):
    _TRACE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    # src/usblm_v1/trace.py -> src/usblm_v1 -> src -> repo root
    _TRACE_DIR = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
_TRACE_DIR = os.path.join(_TRACE_DIR, "logs")
os.makedirs(_TRACE_DIR, exist_ok=True)
_TRACE_PATH = os.path.join(_TRACE_DIR, "v1_shim_trace.log")


def trace(msg):
    try:
        with open(_TRACE_PATH, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass
