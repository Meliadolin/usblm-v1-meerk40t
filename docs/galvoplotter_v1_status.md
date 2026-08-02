# V1 galvoplotter Profile - status: working

Date: 2026-07-31
The V1 translation layer is VERIFIED on hardware. MeerK40t can now
drive the BJJCZ USBLM-V1 board on any modern OS (Win/Mac/Linux/RPi).

## What was needed (the 3 bugs, all fixed)

1. **USB layout** (`V1USBConnection`):
   - find PID 9999 (auto firmware-upload from 9990 loader)
   - commands: 12B galvoplotter packet -> 14B V1 packet (0x0002 prefix)
     on EP 0x01; 2B polls raw; 3072B chunks on EP 0x02 (same as V2)
   - responses: 10B on EP 0x81, return first 8B (galvoplotter unpacks <4H)
   - NEVER close/reopen on timeout (USB reset drops the V1 board to
     loader mode) - retry in place instead

2. **Status semantics** (`V1GalvoController.status/is_ready/is_busy`):
   - V1 state lives in w[3] of the 2-byte 0x0001 poll response, not
     GetVersion's bitmask (galvoplotter's READY=0x20/BUSY=0x04 model
     maps onto 0x0220 idle / 0x0224 running / 0x0226 run-done)
   - is_ready = state == 0x0220 (idle), is_busy = state & 0x04
   - bounded wait_ready (5s) / wait_idle (30s) so a stale board state
     can never hang the flow

3. **THE chunk-ack desync (the real killer)**:
   - The V1 board ANSWERS EVERY 3072B chunk write with a 10-byte
     0x0003 progress response (~10-20ms after the write)
   - galvoplotter sends chunks with read=False -> the ack sits in the
     FIFO -> the NEXT command's read (0x0005 ExecuteList) consumes the
     stale ack -> every subsequent read is one-behind -> status polls
     read garbage ("state" 0x0226/0x0234) -> wait loops hang
   - FIX: `_read_chunk_ack()` - sleep 20ms, read the ack, discard
   - Also: 0x0003 progress handshake must be sent as a 2-BYTE poll
     (like 0x0001), not a 14-byte command

4. **Per-run flow** (marking_configuration/initial_configuration):
   - transition: 0x0009, 0x0034, wait, 0x0012 ResetList, 0x000C,
     0x000D(0x8001,0x8001) home corner, 0x0033(1) MO open, wait
   - list records: 0x8051 listReadyMark, 0x8004(0x0320) open-MO delay,
     0x8011(1) laser port, then galvoplotter set() records
     (0x8006 jump speed, 0x8012 power, 0x801B qswitch, 0x800C mark
     speed, 0x8007/0x8008/0x800F/0x800D delays)
   - chunk padded with 0x8002 end-of-list records (galvoplotter's
     `empty` already does this - EZCAD-identical)
   - execute once (0x0005) + 0x0016(1) SetControlMode, wait idle,
     MO close, home to center (0x000D 0x8000,0x8000)

## Verified on hardware (2026-07-31)
- test_v1_galvoplotter_real.py: connect -> init -> marking() context ->
  square engraved at 15% power -> wait_for_machine_idle() returns ->
  disconnect. Board reports 0x0220 (idle) after the run. FIFO clean.
- test_v1_galvoplotter_mock.py (offline): full flow, chunk structure,
  ExecuteList once, no 0x0019, 0x8002 tail - PASSED

## Usage
    import v1_galvoplotter          # patches galvo.usb_connection
    from v1_galvoplotter import V1GalvoController
    ctrl = V1GalvoController(x=0x8000, y=0x8000, mark_speed=..., power=...)
    with ctrl.marking() as c:
        c.goto(...); c.mark(...)    # galvoplotter plot commands
    ctrl.wait_for_machine_idle()

## Next: MeerK40t
- `pip install meerk40t` + this patched galvoplotter (place the shim
  on the path, or vendor it) -> add device as EZCAD2/JCZ galvo
- MeerK40t is MIT, cross-platform, no drivers, no dongle

## Files
- v1_galvoplotter.py      - the profile (transport + controller)
- test_v1_galvoplotter_mock.py - offline flow test
- test_v1_galvoplotter_real.py - hardware test (square @ 15%)
- diag_*.py               - the diagnostic scripts used to get here
- data/fw_capture4.pcap   - vector session capture (run-end decoding)
- data/fw_capture5.pcap   - raster session capture (raster decoding)

================================================================
MEERK40T (balormk) SHIM - STATUS: WORKING ? (2026-07-31)
================================================================
v1_meerk40t.py patches meerk40t.balormk for the V1 board. Verified
on hardware: connect -> V1 init -> program_mode -> settings+marks ->
rapid_mode -> execute -> IDLE 0x0220 -> wait_finished returns.

Differences from the standalone galvoplotter shim (all handled):
- balormk's wait_ready/wait_idle have NO timeout -> overridden (5s/30s)
- balormk's init_laser sends 0x0040 Reset + serial query -> overridden
  with the verified V1 init sequence
- balormk's rapid_mode lacks 0x0016(1) SetControlMode after execute
  -> override adds it
- balormk's program_mode sent realtime 0x0021(1) -> removed (the
  0x8011 record carries the port bits)
- THE critical piece: 2-byte 0x0003 progress handshake BEFORE the
  chunk send (without it the board never accepts the chunk - the
  write times out and retries 4x, then execute does nothing, state
  stays 0x0226)
- chunk-ack drain after the chunk send (same as standalone)

Patch sites: meerk40t.balormk.usb_connection.USBConnection,
controller.USBConnection, controller.GalvoController,
driver.GalvoController.

IMPORT: import v1_meerk40t BEFORE creating the Balor device.

================================================================
CAPABILITY MATRIX - COMPLETE (2026-08-01, hardware verified)
================================================================
test_capabilities.py exercises every code balormk can emit:
- ALL realtime commands respond OK (DisableLaser 0x0002, GetListStatus
  0x000A, LaserSignalOn/Off 0x000E/0x000F, WriteCorLine 0x0010,
  RestartList 0x0013, SetMaxPolyDelay 0x0018, StopList 0x0020,
  WriteAnalogPort2/X 0x0023/0x0024, ReadPort 0x0025, GetFlyWaitCount
  0x002B, GetMarkCount 0x002D, SetFpkParam2 0x002E, DisableZ 0x0039,
  SetZData 0x003B, SetSPISimmerCurrent 0x003C, Reset 0x0040)
- ALL list records execute in jobs OK (dwell 0x8003, mark-count 0x8023,
  in-list MO 0x8021, YLPM pulse width 0x8026, DA Z-word 0x8029,
  fly delay 0x801D)
- LIGHT MODE OK (light_mode override: V1 transition + guaranteed
  0x8006 speed record + configurable light pin)
- AXIS commands respond; leave AXIS flag (state 0x260) which is
  harmless (ready+not-busy both still true for marking)
- Raster: verified earlier (EZCAD-style pixel records)
- Firmware upload: verified (loader mode)
=> SHIM COVERAGE: everything MeerK40t can emit.
