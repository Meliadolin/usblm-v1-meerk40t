# BJJCZ USBLM-V1 Protocol - verified reference

Extracted from USBPcap captures of EZCAD 2.5.3 (Win7), cross-checked against
the LMCUSB.sys binary, the galvoplotter library, and **live tests on the
physical board**. Every sequence here is proven to work.

## Endpoints (interface 0, vendor class ff, 6 bulk eps, wMaxPacketSize 512)

| EP | Direction | Purpose |
|---|---|---|
| 0x01 | OUT | command channel |
| 0x81 | IN | response channel (10 bytes = 5 × uint16 LE) |
| 0x02 | OUT | list/chunk channel (3072-byte chunks = 256 records × 12 B) |
| 0x04 / 0x86 / 0x88 | - | unused |

## Command packet (EP 0x01)

- 14 bytes: `[0x0002, code, p1, p2, p3, p4, p5]` (7 × uint16 LE)
- 4 bytes: `[0x0004, 0x0003]` (progress handshake)
- 2 bytes: `0x0001` (status poll) / `0x0003` (progress poll)
- Response: 10 bytes = 5 words: `[echo...][status][flags]`
  - `w[3]` = state: `0x0220` IDLE, `0x0224` RUNNING
  - `w[4]` = `0x8000` while running

State stays `0x0224` for the **whole** run; completion means `w[3]` returns
to `0x0220`. Polls never stop responding - do not use silence detection.
EZCAD polls roughly 3900×/sec in a tight loop.

**Two running states (verified live):**
- `0x0224` = vector list running (no power records)
- `0x0234` = raster-style list running (power records 0x8012 present)

Both are legitimate and must never be interrupted - a raster job can run
for minutes. `0x0220` = idle. `0x0200` = not ready (list buffer full,
see the streaming note below). `0x0226` = run-done with the list still
open (a stuck state - clear with the stop sequence).

## Commands

| Code | Name | Notes |
|---|---|---|
| 0x0001 | GetStatus | status poll |
| 0x0002 | DisableLaser | |
| 0x0004 | EnableLaser | init only |
| 0x0005 | ExecuteList | run the buffered job |
| 0x0006 | SetPwmPulseWidth | |
| 0x0007 | GetVersion | -> 0x1247 |
| 0x0009 | Reset/GetSerialNo | |
| 0x000C | GetPositionXY | |
| 0x000D | GotoXY | |
| 0x0012 | ResetList | |
| 0x0015 | WriteCorTable | cor file upload (payload format unverified) |
| 0x0016 | SetControlMode | |
| 0x0017 | SetDelayMode | |
| 0x0019 | SetEndOfList | realtime variant; chunks carry 0x8002 padding instead |
| 0x001A | SetFirstPulseKiller | |
| 0x001B | SetLaserMode | |
| 0x001C | SetTiming | |
| 0x001D | SetStandby | (2000, 20, 1) |
| 0x001E | SetPwmHalfPeriod | |
| 0x001F | StopExecute | |
| 0x0021 | WritePort | |
| 0x0022 | WriteAnalogPort1 | init only |
| 0x0033 | Fiber_SetMo | 0 = close, 1 = OPEN (laser fires on marks) |
| 0x0034 | Fiber_GetStMO_AP | |
| 0x003A | EnableZ | |
| 0x0040 | Reset | |
| 0x0062 | SetFpkParam | |

## List records (EP 0x02, 12 bytes = 6 × uint16 LE)

`[opcode, v1, v2, v3, dist, 0]`

| Opcode | Meaning |
|---|---|
| 0x8001 | listJumpTo |
| 0x8002 | listEndOfList (terminator/padding) |
| 0x8003 | listLaserOnPoint |
| 0x8004 | listDelayTime |
| 0x8005 | listMarkTo |
| 0x8006 | listJumpSpeed |
| 0x8007 | listLaserOnDelay |
| 0x8008 | listLaserOffDelay |
| 0x800A | listMarkFreq |
| 0x800B | listMarkPowerRatio |
| 0x800C | listMarkSpeed |
| 0x800D | listJumpDelay |
| 0x800F | listPolygonDelay |
| 0x8011 | listWritePort |
| 0x8012 | listMarkCurrent (power) |
| 0x801B | listQSwitchPeriod (frequency) |
| 0x8021 | listFiberOpenMO |
| 0x8051 | listReadyMark |

- `dist` = euclidean distance from the previous point (0-0xFFFF)
- mark flag in word 3: `0x8000` = laser on (EZCAD also uses 0x4000 for some
  marks; 0x8000 works for all)

## Init sequence (EZCAD 2.5.3)

Includes EnableLaser and the laser config; sent once per session, not per
run:

```
0x0009, 0x0007(1)->0x1247, 0x0003(4-byte), 0x0007(1),
0x0015, 0x0004(EnableLaser), 0x0016(0), 0x001B(1), 0x0017(1),
0x001C(1), 0x001D(2000,20,1), 0x001A(200), 0x001E(50), 0x0006(50),
0x0033, poll, 0x0062(0xFFB,1,0x199,100), 0x0007(1),
0x0032-variant [0x0006,0x0032,0,0xA3,0x3E8,0x19],
0x0021(0), 0x003A(EnableZ)
```

## Run sequence (verified, first run after init)

```
Transition: 0x0009, 0x0034, poll, 0x0012, 0x000C,
            0x000D(0x8001,0x8001), 0x0033(1)   <- MO open = the per-run trigger
Queue:      for each chunk: write EP 0x02, then poll 0x0001, poll 0x0003
Execute:    0x0005 (ExecuteList), 0x0016(1)
Wait:       poll 0x0001 fast (5 ms) until w[3] == 0x0220 (IDLE)
Done:       0x000D(0x8000, 0x8000)  <- return galvo to center
```

End of session (EZCAD): `0x0012, 0x0033(1), 0x0016(1), 0x0021(0), 0x001D, 0x0033`

## Critical: buffered job model (not streaming)

The board buffers the **entire** job internally:

- EZCAD sends ALL chunks (13 × 3072 B = 40 KB for a big fill) back to back
  with poll-pairs between, **before** ExecuteList
- then does nothing for 82 seconds while the board executes
- polling ~3900×/sec the whole time (state stays 0x0224)

**Do not re-send chunks during execution** - it overwrites the buffer and
only the last chunk executes (the "only diagonal ran" bug).

**The board's list buffer is finite (verified live).** A jump-only list
can exceed 360 chunks, but power-record-heavy lists (raster) fill the
buffer after a few hundred chunks - the board then stops reporting READY
(state `0x0200`) until the list is executed. Large jobs must be split
into chained batches: execute what is queued (the last chunk's 0x8002
padding ends the mini-list), wait for the run, reset the list, and keep
sending. This is exactly EZCAD's raster streaming behavior - the shim's
`_list_end` does this automatically when the board signals full.

## Speed scale

```
real speed = speed_record × 778 units/sec
```

EZCAD example: mark speed 419 -> 326,094 u/s (3123 marks, 27M units, 82.9 s).
Duration estimate: `total_dist / (mark_speed × 778)`.

## Multi-direction fill = one job

H+V+D fills are one list (192+ segments, multiple chunks), not separate
runs - the galvo just moves between segments.

## Fiber laser (critical)

- `0x0004` EnableLaser and `0x0022` WriteAnalogPort1(0x7FF) are sent **once
  at init**, not per run.
- The per-run laser trigger is `0x0033` Fiber_SetMo = **1** (OPEN).
- Without MO open, the laser moves but never fires.

## Firmware upload (loader PID_9990)

Standard Cypress FX2LP loader protocol:

```
ctrl_transfer(0x40, 0xA0, addr, 0, data)   # vendor request to FX2 RAM
```

- 501 writes, 6.8 KB image at 0x0000-0x1FFF
- order: 0xE600=0x01 (CPUCS halt), chunks, 0x14C9=0x00, 0xE600=0x00 (start)
- validated: 499/501 identical to the LMCUSB.sys embedded table
- replay file: `data/v1_upload_sequence.dat`

## Recovery (CPUCS reset, no replug)

```
ctrl_transfer(0x40, 0xA0, 0xE600, 0, b'\x01')  then b'\x00'
```

Do **not** use a USB bus reset - it drops the board into loader mode
(balormk's default disconnect does a bus reset; the V1 shim disables it).

## The end-of-list terminator

Every list must end with an explicit 0x8002 end-of-list record + a
terminator chunk before ExecuteList. Executing a list without it makes
the board wait forever (state 0x234) - the light/outline trace mode hit
this until the shim started ending light passes like normal jobs.

## Raster engraving (decoded 2026-07-31, fw_capture5.pcap)

EZCAD processes the bitmap **fully on the PC** - the board has no raster
logic. The bitmap becomes plain list records:

```
Per scan line:  0x801C(0x0000)  line marker 1
                0x8006 jump_speed
                0x8001 jump to line start
                0x8006 mark_speed
                0x801C(0x000A)  line marker 2
Per pixel:      0x8012 power(pixel gray value)   <- the image data
                0x8005 mark, fixed step 0x002A (42 units ~0.08 mm)
```

- 19 lines captured, two power levels (0x0199=409, 0x02CC=716) = black
  square with anti-aliased edges
- scan direction mostly leftward, short rightward returns
- chunks re-sent continuously during the run (streaming model)
- no special endpoints used
- raster = generate pixel records + mark_job(). Done.

## Device setup (markcfg0 + CoeFile.cfg from the machine)

`markcfg0` (Plug/markcfg0 - the exact file LightBurn asks for):

```
FIELDSIZE = 100.0 mm      (100×100 mm galvo field)
FIELDOFFSETX/Y = 0, FIELDANGLE = 0, GALVOX = 1 (no mirror)
LASERTYPE = 3 (fiber), ENPWMOUT = 1, 20-200 kHz, ENPWMTICK = 1
ENFPK = 1, FPK = 40
STARTCMDBLOCK = 2
Rotary: AXISID 0/1, 200 steps/rev, 5 mm/rev, ±1000 mm, 100-5000 mm/s
ENSTARTMARKSIGNAL = 1, ENFLYMARK = 0
REDLIGHTSPEED = 3000 mm/s
```

Scale: 100 mm field / 65536 units = **~655 units/mm** (0x8000 = center).

`CoeFile.cfg` (68 KB binary correction coefficients) exists on the machine,
but the 0x0015 upload payload format is unverified - captures show 0x0015
sent with no payload. The board runs fine without lens correction.

## Captures

Raw .pcap captures stay local (in `data/`); the decoded chunks are
committed as protocol evidence.

| File | Content |
|---|---|
| fw_capture.pcap | first capture - init + test |
| fw_capture2.pcap | outline + single mark session |
| fw_capture3.pcap | firmware upload (loader -> normal) |
| fw_capture4.pcap | vector + run-end session |
| fw_capture5.pcap | raster session (decoded above) |
| fw_markrun.pcap | multi-chunk fill (3123 marks, 82.9 s) - the key one |
| fw_upload.pcap | 115 MB all-hubs capture (reference) |
| ezcad_chunk_0..12.bin | the 13 actual chunks of the fill job |
