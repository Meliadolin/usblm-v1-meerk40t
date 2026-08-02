# Troubleshooting

Every item here is something that actually happened and was fixed. If your
symptom isn't here, the logs will name it: everything writes to the
`logs\` folder next to the exe (`install_log.txt`, `selftest_log.txt`,
`diag_info.log`, `v1_shim_trace.log`, `meerk_trace.log`, `panel_log.txt`,
`bind_winusb_log.txt`, `upload_log.txt`).

**Reporting a problem:** reproduce it, then send the `logs\` folder from
the package folder plus a Device Manager screenshot of the board.
`v1_shim_trace.log` is the protocol-level trace (USB reads/writes, states)
and `meerk_trace.log` captures any Python traceback - together they usually
pinpoint the fault exactly.

## Symptom -> cause -> fix

### "No module named 'usb'" when running the scripts
The software install step didn't run (or pip failed). Run
`SetupPanel.exe` and press **1. Install Software**, then check
`logs\install_log.txt`.
`scripts\selftest.cmd`/`scripts\diag.cmd`/`scripts\run_meerk40t.cmd`
deliberately do not install anything - they only run.

### Board not found - "board found" FAIL in selftest
Three possible causes, in order of likelihood:

1. **WinUSB not bound.** Device Manager should show the board with
   Service = WinUSB. Fix: plug the board in, run `scripts\bind_winusb.cmd`
   (it asks for permission itself - click Yes). The board will
   re-enumerate (briefly disappear and reappear in Device Manager)
   when the driver lands - that is normal.
2. **libusb-1.0.dll not loadable.** pyusb finds the DLL via
   `ctypes.util.find_library()`, which on Windows searches only next to
   python.exe and in PATH. It does **not** look at
   `os.add_dll_directory()` folders - if the DLL can't be found the
   backend fails *silently* and libusb sees **zero** devices, even though
   Windows itself shows the board fine. `libusb_bootstrap.py` (imported
   first by everything) solves this; if it was copied to a new folder
   without `libusb-1.0.dll` beside it, put the DLL back next to it.
   `scripts\diag.cmd` prints exactly which candidate locations it searched.
3. **The board is in loader mode** (PID 9990) and the firmware upload
   failed. See below.

### Board shows "Unknown Device #1"
**This is normal** - it's the board in loader mode (PID 9990), which is
what it does until the firmware upload runs. The shim auto-uploads on
connect; if it never gets to upload, run `upload_firmware.py` by hand or
replug the board and run the selftest again.

### GUI opens but crashes / does nothing
Check `logs\meerk_trace.log` - it captures stderr including the Python
traceback (the exe has no console). Common causes:

- **wxPython too new.** MeerK40t 0.9.9100 requires wxPython **4.2.x**;
  the panel code crashes with `wxAssertionError: page must be a child of
  the notebook` on 4.3.x. The installer pins 4.2.2 - if you installed
  packages yourself, check the version.
- the shim failed to load -> `SHIM LOAD FAILED` is logged.

### Selftest passes but the board doesn't mark
- Laser power 0 / MO closed - check Device settings.
- Check the E-stop is released (press = STOP; ours was wired
  backwards from the factory - verify on every machine).
- The beam may be invisible (IR laser) - the job could be running
  while you see nothing. Test with a small mark on scrap material at
  low power.

### Only part of a raster/text job gets engraved
- The board has TWO legitimate running states: `0x0224` (vector) and
  `0x0234` (raster with power records). Early shim versions mistook
  0x0234 for a wedge and stopped the job after 2 seconds - the current
  shim waits for both states and never interrupts a running job.
- Big jobs stream automatically: when the board's list buffer fills
  (state 0x0200, not-ready), the queued batch is executed, the list
  reset, and sending continues. A visible pause between batches is
  normal for very large jobs.

### A job "takes a long time to begin"
- If a LiveLightJob (outline) is still running in the spooler, new jobs
  queue behind it - stop the light job first.
- After a crashed/aborted session, the board may be in a leftover
  state; the shim self-heals on the next connect, but replugging is the
  quickest clean start.

### Board shows up as loader mode (9990) after every session
- Fixed in the current shim: balormk's default disconnect does a USB
  bus reset, which drops the V1 board into loader mode. The V1 shim
  disables the reset. Old builds and sessions ended by force (kill,
  crash) still leave the board in loader mode until the next connect
  (which auto-uploads) or a replug.

### Job hangs in MeerK40t
Close the GUI, check `logs\meerk_trace.log` and `logs\v1_shim_trace.log`.
The shim has bounded waits and self-healing reads - a hang means a
USB-level problem (driver binding, cable) rather than a protocol
deadlock. Replug the board, rerun the selftest.

### Mark is mirrored or rotated
Device Settings > flip_y / swap_xy. Test with a letter, not a symmetric
shape.

### pip install fails on the target PC
The install is fully offline - if it fails there's no internet problem to
blame. Check `logs\install_log.txt` for the pip error; a corrupted copy
(failed copy to a USB drive) is the usual suspect. Re-copy the package
folder.

### install.bat says "python not found"
`where python` in an **elevated** window searches the *admin* PATH, which
often lacks what your normal user PATH has. The installer falls back
through several known locations; if all fail, install Python 3.12 x64
and run scripts\install.bat again.

## Design notes (why some things look odd)

- **Redlight button / `red` command does nothing visible.** On some
  machines the aiming dot is wired directly to the laser power supply and
  is simply always on - the board's GPIO does not control it (verified
  live: cycling all port bits changed nothing). The light pin setting
  only matters if your machine actually drives the dot from a GPIO.
- **No elevation outside install steps.** `scripts\install.bat` and
  `scripts\bind_winusb.cmd` self-elevate; everything else (GUI, selftest,
  diag) runs as the normal user on purpose.
- **No bus resets.** A USB bus reset drops the board into loader mode.
  Recovery without replug: CPUCS reset, see `docs/PROTOCOL.md`.
- **Do not stream chunks during a run.** The board buffers the whole job;
  re-sending overwrites the buffer (see the buffered job model in
  `docs/PROTOCOL.md`).
