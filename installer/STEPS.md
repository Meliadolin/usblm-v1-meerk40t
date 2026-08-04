# USBLM-V1 + MeerK40t - Plug & Play (fresh PC)

**Everything needed is in this folder.** No Python install, nothing to
download. Windows 10/11 64-bit is all you need.

## EASY WAY - SetupPanel.exe (recommended)

1. Extract the downloaded package (if you haven't already) and open this
   folder
2. Double-click **`SetupPanel.exe`** - a control panel opens
3. Click the buttons in order:
   - **1. Install Software** - extracts the bundled Python
     into `runtime\`, installs all packages from this folder, deploys
     device settings, creates the desktop shortcut. Progress appears
     right in the panel.
   - **2. Install USB Driver** - binds the board to WinUSB with
     `zadig.exe` (the signed driver tool in `tools\`; plug the laser
     in first; Windows asks for permission, click Yes; then in the
     Zadig window pick "USBLM-V1" and click **Install Driver**)
   - **3. Run Self-Test** - output appears right in the panel
     (expect: RESULT: 5 passed, 0 failed)
   - **4. Launch MeerK40t** - the marking app opens
4. Alternatively: use the desktop shortcut "MeerK40t V1" that was created

## CLASSIC WAY - the scripts

Everything the panel does is also available as scripts in `scripts\`:

| Script | What it does |
|---|---|
| `scripts\install.bat` | Install software (no admin needed) |
| `scripts\bind_winusb.cmd` | WinUSB binding (admin) |
| `scripts\selftest.cmd` | 5-check verification |
| `scripts\diag.cmd` | Diagnostics (run if anything fails) |
| `scripts\run_meerk40t.cmd` | Launch the marking app |

## Notes

- **MeerK40t-V1.exe** - the marking software with the USBLM-V1 device
  profile compiled in.
  It is also launched by the panel/shortcut; it runs standalone.
- Everything logs to the `logs\` folder next to the exe.

## First time you plug the laser in

This is what happens, step by step, and what every screen means.

### The moment you plug the board in (before any driver)

Windows plays the "new device" sound. The board shows up in Device
Manager as **one of these two things** - both are normal, neither is
broken:

| What Device Manager shows | What it is |
|---|---|
| **"USBLM-V1"** with a yellow warning triangle | The board in normal mode (PID 9999), no driver installed yet |
| **"Unknown Device #1"** | The board in loader mode (PID 9990) - this is its bootloader, and it has no driver yet |

"Unknown Device #1" is **not** a problem. It just means Windows has
no driver for this particular device *yet* - it is Windows' generic
name for anything it can't identify. The laser board always boots
into loader mode if it has never been started since it was made, and
it returns there after a firmware update. The software uploads the
firmware automatically and switches it to normal mode.

If Windows pops up "What do you want to do with this device?" or
offers to search online for drivers: close it / choose "Do nothing".
The driver is installed in the next step.

> Note: until the driver is installed, the software cannot see the
> board at all (it only talks to boards that have the WinUSB driver).
> So "board not found" before step 2 is expected, not an error.

### After clicking "2. Install USB Driver"

1. Windows asks for permission - click **Yes**.
2. A Zadig window opens (Zadig is the signed driver tool that ships in
   this folder - it is pre-configured to list *all* devices, select
   WinUSB, and close by itself when the install succeeds).
3. In the dropdown pick the board: **"USBLM-V1"** (VID 9588 - PID 9999
   in normal mode, 9990 in loader mode). WinUSB is already selected as
   the driver. Click **Install Driver**. If the board is hard to spot,
   use the menu File > Open > `usblm-v1.ini` to pre-fill the VID/PID
   fields.
4. The board re-enumerates: it disappears from Device Manager for a
   second or two and comes back. This is normal and by design -
   **do not unplug it during this**.
5. Device Manager now shows the board as **"USBLM-V1"** with no
   warning triangle, service **WinUSB**, whichever mode it is in.
6. To double-check: right-click the device > **Properties** >
   **Driver** tab; the driver provider should read *Microsoft*
   (WinUSB is a Microsoft driver).

### Re-enumeration - "the board vanished!" explained

The board re-enumerates (disappears and reappears in Device Manager)
**twice during setup**, both times by design:

- when the WinUSB driver binds (step 2 above)
- after the firmware upload, when it switches from loader mode to
  normal mode (happens automatically the first time the software
  starts)

It is gone for one or two seconds, then comes back by itself. The
software waits for this too: if it says "board not found" or "board
in loader mode", give it a few seconds and it retries automatically.

### "What am I looking at?" quick reference

| You see | Means | Do |
|---|---|---|
| Nothing happens when you plug in | USB port or cable problem | try another port / cable |
| Yellow triangle on the board | Normal mode, driver not installed yet | click button 2 |
| "Unknown Device #1" | Loader mode (bootloader), driver not installed yet | click button 2 - same fix |
| Board flickers in/out of Device Manager | Re-enumeration (by design) | wait a few seconds, do nothing |
| "Unknown Device #1" still there after button 2 | The driver did not bind for the loader | run `scripts\diag.cmd`, check `logs\diag_info.log` |
| Self-test says "board not found" | Usually just re-enumeration in progress | wait 2-3 seconds, run self-test again |
| Self-test says "board in loader mode" | Firmware upload is running automatically | wait - it finishes by itself |

The self-test (button 3) is the source of truth: it checks the
actual driver state (`bound driver per PID` -> must be WinUSB) and
talks to the board directly. Device Manager is only for reference.

## If something fails

Run `scripts\diag.cmd` and open `logs\diag_info.log` - it checks:
1. `TOTAL devices visible to libusb: N` (N>=3 = USB stack OK)
2. `PID 9999/9990` FOUND?
3. `bound driver per PID` -> Service must be WinUSB

Bring back the `logs\` folder: `install_log.txt`, `selftest_log.txt`,
`diag_info.log`, `v1_shim_trace.log`, `meerk_trace.log` (everything
logs into `logs\`).

Everything is logged. The logs name the culprit.
