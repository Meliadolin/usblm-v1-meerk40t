# Translation Layer Research - Modern Marking Software for USBLM-V1
Research date: 2026-07-31
Status: RESEARCH (no board changes made)

## The problem
V1 board: VID 9588, PID 9999 (normal) / 9990 (loader).
EZCAD 2.5.3 is stuck in 2006-era. Modern software needs a "translation layer".

## THE KEY FINDING
The official JCZ 64-bit signed driver package (drivers/bj jcz-64bit-driver, already
installed on this PC as C:\Windows\System32\drivers\Lmcv2u.sys) matches ALL FOUR
board PIDs (Lmcv2u.inf):

    USB\VID_9588&PID_9980  -> LMC V2 loader
    USB\VID_9588&PID_9899  -> LMC V2 normal
    USB\VID_9588&PID_9999  -> LMC V1 normal   <-- OUR BOARD
    USB\VID_9588&PID_9990  -> LMC V1 loader

=> The V1 board is officially supported by the signed V2 driver stack.
=> THAT is why EZCAD 2.5.3 ran on Win10 x64 (Lmcv2u.sys claimed PID 9999).
=> For kernel-driver software (EZCAD family): driver layer already solved,
   just install "bj jcz-64bit-driver" on the target PC.

## Software landscape (who speaks what)

| Software          | Protocol layer          | V1 board?             | License  | Platforms        |
|-------------------|-------------------------|-----------------------|----------|------------------|
| EZCAD 2.5.3       | LMCUSB/Lmcv2u + LMC1    | YES (native)          | Free     | Windows          |
| EZCAD 2.14.11     | Lmc1.dll/LmcLib/LMCMIO  | YES (LMC1 API kept)   | Free     | Windows          |
| EZCAD 2.14 LITE   | same as 2.14            | YES                   | Free     | Windows          |
| EZCAD3            | LMCV3 protocol, new hw  | NO                    | Paid     | Windows          |
| LightBurn Pro     | galvoplotter (LMC V2)   | NO (hardcoded 9899)   | ~$200    | Win/Mac/Linux    |
| MeerK40t          | galvoplotter (LMC V2)   | NO (same)             | MIT      | Win/Mac/Linux/RPi|
| galvoplotter lib  | LMC V2 direct-USB       | NO (same)             | MIT      | Python (any OS)  |
| balor (Bryce)     | LMC V4 (BJJCZ_LMCV4)    | NO                    | SSPL v1  | Python CLI       |
| SeaCAD / BSL      | different JCZ family    | NO                    | Paid     | Windows          |

## Why LightBurn/MeerK40t don't see our board
galvoplotter (github.com/meerk40t/galvoplotter, MIT, by Tatarize - the library
LightBurn's galvo backend derives from AND what MeerK40t uses) hardcodes in
galvo/usb_connection.py:

    USB_LOCK_VENDOR  = 0x9588
    USB_LOCK_PRODUCT = 0x9899   <- V2 board PID only
    WRITE_ENDPOINT   = 0x02     <- V2 uses EP0x02 for BOTH commands and lists
    READ_ENDPOINT    = 0x88     <- V2 reads 8-byte (4-word) responses

V1 differences (verified):
    PID 9999 (not 9899), EP 0x01/0x81 for commands, 10-byte (5-word) responses,
    poll-pair required between list chunks, firmware upload from PID 9990.

## Translation layer options (ranked)

### Option 1: PATCH GALVOPLOTTER for V1  (RECOMMENDED, the real "any PC" win)
- MIT open source, active (108 commits), maintained by MeerK40t author.
- Add a V1 profile: accept PID 9999/9990, EP 0x01/0x81 command+response,
  EP 0x02 for lists, 10-byte reads, poll-pair chunk flow, firmware upload.
- Effect: MeerK40t (free full GUI laser software, Win/Mac/Linux/RPi) works
  with our board on ANY PC - no drivers, just pip install + libusb.
- Bonus: upstream PR -> LightBurn could adopt it for future releases.
- We already have all protocol knowledge verified in v1_controller.py.

### Option 2: TEST V1 firmware on EP 0x02/0x88 (cheap experiment, enables LightBurn)
- V1 board ALREADY has EP 0x02 OUT and EP 0x88 IN in its config descriptor.
- Experiment: send a command (e.g. 0x0009 GetVersion) to EP 0x02, read EP 0x88.
  If firmware responds -> V2-style channel works on V1 hardware.
- If yes: rewrite EEPROM descriptors (PID 9999 -> 9899, endpoints stay) and
  galvoplotter/LightBurn/MeerK40t find and talk to the board UNCHANGED.
- Risk: EEPROM reprogramming; recoverable (we already self-boot via EEPROM).

### Option 3: EZCAD 2.14.11 on this PC (test immediately, likely just works)
- EZCAD 2.14 still ships Lmc1.dll/LmcLib.dll/LMCMIO.dll (LMC1 = V1 protocol).
- Lmcv2u.sys already installed here and claims PID 9999.
- Lmc1.dll opens the driver via SetupAPI+DeviceIoControl (no libusb).
- Likely: install EzCad2.14.11 -> it detects our V1 board -> modern EZCAD UI
  (pen settings, hatches, serial numbers, etc.) with NO translation needed.
- Test plan: run EzCad2.exe, check board detection, mark a test square.

### Option 4: USB virtual device (UsbDk) - LAST resort
- Userspace emulation of a V2 device; our controller underneath.
- Works with LightBurn/EZCAD unchanged, but heavy engineering + kernel dep.

## Recommended next steps
1. Test EZCAD 2.14.11 (Option 3) - 10 minutes, may give full modern UI now.
2. Run EP 0x02/0x88 experiment (Option 2) - 5 minutes, no risk (no EEPROM yet).
3. Implement galvoplotter V1 support (Option 1) - the cross-platform deliverable.
4. Only if 2 succeeds: EEPROM PID change for LightBurn direct support.

## Files
- drivers/bj jcz-64bit-driver/  - signed V2 driver matching ALL PIDs (install on any PC)
- drivers/EzCad2.14.11/         - newer EZCAD with LMC1 (V1) API + markcfg0/markcfg7
- drivers/EzCadLITE_2.14.16/    - LITE version (LMC1 too)
- drivers/EzCad2.5.3/           - original software
- site-packages/galvo/          - galvoplotter 0.2.0 (patch target)
- github.com/meerk40t/galvoplotter - upstream
- gitlab.com/bryce15/balor      - original RE project (LMCV4 only)
