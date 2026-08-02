# USB Capture Jobs - Settings for EZCAD 2.5.3 (Win7 laptop)

Goal: capture EZCAD 2.5.3 sessions with USBPcap so we can (a) fix the
galvoplotter V1 run-end bug (0x0226) and (b) decode the raster data path.

## What to take to the laptop
- The USB dongle (it's currently plugged into THIS PC - EZCAD needs it)
- The laser board + cable
- `data/capture_jobs/capture_raster.bmp` (32x32 black square)
- The USB drive with `D:\capture.cmd` (USBPcap capture helper)

## Pen 1 settings (same for ALL jobs)
- Mark speed:   100 mm/s
- Power:        15 %
- Frequency:    20 kHz (20000 Hz)
- Q-pulse width: 100 us (default)
- Jump speed:   1000 mm/s (default)
- Laser on / off / end / polygon delays: defaults
- Mark loop:    1

## Jobs to create (one project file with 4 entities, or 4 files)

1. **SQUARE** - one 8 x 8 mm square, centered, outline only (no hatch)
2. **SQUARE_LONG** - four concentric squares: 8, 6, 4, 2 mm, centered
3. **HATCHED** - one 8 x 8 mm square, centered, WITH hatch fill
   (right-click entity -> hatch, line fill, default angle/spacing)
4. **RASTER** - import capture_raster.bmp, place at center, black = mark

## Capture procedure (exactly one capture file for all four)
1. Boot laptop, plug dongle + board, start EZCAD 2.5.3
2. Start USBPcap capture (use D:\capture.cmd, 180s window is fine)
3. Mark job 1 (SQUARE) - wait for the run to FULLY finish
4. Wait ~5 seconds (this gap matters - we study the post-run state)
5. Mark job 2 (SQUARE_LONG) - wait, ~5s gap
6. Mark job 3 (HATCHED) - wait, ~5s gap
7. Select RASTER entity only, mark it - wait, ~5s gap
8. Stop the capture, save the .pcap

Total EZCAD window: ~120 seconds if done briskly.

## What the captures will tell us
- Capture 1-3: the exact post-run command sequence + state words
  (0x0224 -> 0x0220 vs 0x0226) -> fixes the galvoplotter hang
- Capture 4: the raster data path (likely EP 0x04 / BmpBuffer commands)
  -> completes our "full control" coverage
