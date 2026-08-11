# Changelog

## 1.1.1 - 2026-08-11

Bugfix release for the native device profile.

- Config window now opens with all device tabs. The V1 choice sections
  are registered under the balor* names the reused upstream panel looks
  up, and the window stays open while the V1 is the active device.
- Firmware upload is guarded: a missing sequence file or an unclaimable
  loader reports a clear error instead of crashing the connect path.
- abort() runs under the list lock so a reset can never land mid-chunk
  and wedge the board firmware.
- Footpedal reads are V1-safe: the board does not answer the balormk
  read-port command, so the poll logs once and stays inert instead of
  spamming errors during jobs.
- Default power aligned to the shipped config (300 permille).
- Trace log renamed from v1_shim_trace.log to v1_trace.log.
- Offline CI passes 16/16, including the registration test updated for
  the renamed choice sections.

## 1.1.0 - 2026-08-05

The V1 board is now a native MeerK40t device. `src/usblm_v1/` registers
its own device provider (`provider/device/usblmv1`) - the board shows up
in the GUI as its own device, USBLM-V1, next to the stock balormk
devices. No more patching of balormk classes.

- The profile is pip-installable into an existing MeerK40t install:
  `pip install usblm_v1-1.1.0-py3-none-any.whl` (attached to this
  release), or `pip install .` from the repo. The board appears in the
  device dialog automatically. (The official MeerK40t Windows installer
  cannot load plugins - use the package zip for that one.)
- Hardware-verified through the MeerK40t GUI: marking, multi-direction
  fills, raster engraving, red-light trace and live-outline. The marking
  beam was visually confirmed on material.
- Beam gate fix: `0x0022 WriteAnalogPort1(0x7FF)` is now sent at init by
  all three drivers (profile, standalone controller, galvoplotter). The
  standalone engine previously moved the galvo but never fired the laser.
- Connect-time healing: leftover list states (0x226/0x236/0x234) are
  stopped with the verified 0x001F-first ladder before any job runs, so
  a crashed or aborted test can never wedge the next session.
- Deterministic stream close: the streaming outline path reboots the
  firmware in place (CPUCS) after the run, so a stream can never leave
  the board wedged for the next job.
- Self-healing USB: stale responses are drained and re-synced; connect
  reboots and re-attaches if the command channel is dead.
- Offline CI battery (16 checks) passes. The registration test verifies
  both the launcher path and the stock entry-point path.

## 1.0.0 - 2026-08-02

First release. Userspace USB controller for the V1 board, automatic
firmware upload (loader 9990 -> marking device 9999), the reverse-
engineered EZCAD 2.5.3 wire protocol, and the first MeerK40t
integration (shim-based).
