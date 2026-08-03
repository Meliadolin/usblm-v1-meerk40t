# Reverse engineering the V1 protocol

This is how the protocol in `PROTOCOL.md` was obtained, and how you can do
the same for another board. Everything here uses only observation of what
the vendor software sends over USB - no disassembly of the board, no vendor
source code.

## The toolchain

| Tool | Role |
|---|---|
| USBPcap (free, Wireshark's capture driver) | USB packet capture on Windows |
| Wireshark | read the .pcap, follow USB transfer streams |
| Python + pyusb | probe the board directly (send/receive) |
| galvoplotter (MIT, open source) | its command constants + protocol expectations |
| The vendor's own Windows software | the thing observed (EZCAD 2.5.3 here) |

You also need a machine that runs the vendor software. For EZCAD that means
a 32-bit Windows box with the license dongle - the board itself is a dumb
USB device, so its side of the wire is identical regardless of which PC is
at the other end.

## Step 1: capture a real session

1. Install USBPcap, start a capture on the root hub the board is on
   (an all-hubs filter capture catches everything).
2. Run the vendor software and do a few well-chosen jobs, with pauses
   between them. Each job should be simple and different:
   - one outline square (no fill)
   - one filled/hatched square
   - one raster engraving of a known bitmap
   - one firmware upload (replug the board so the loader runs)
3. Stop the capture. You now have the vendor talking to the board.

## Step 2: sort the noise from the signal

USBPcap gives you every USB transfer, including the vendor software's
polling. The useful pattern in the captures:

- the board's endpoints are visible as `2.1.0` / `2.2.0` (config/interface)
- bulk transfers on EP 0x01 OUT / EP 0x81 IN are the command channel
- bulk transfers on EP 0x02 OUT are the list/job data channel
- control transfers to the FX2 (0xA0 vendor request) are the firmware upload

`fw_markrun.pcap` was the key capture: a big fill job where EZCAD
queues 13 chunks of 3072 bytes, then sits and polls for 82 seconds while
the board executes. That one capture proved the buffered job model.

## Step 3: identify the commands

The command channel packets are short and repetitive, so you can identify
them by shape:

- a 14-byte write followed by a 10-byte read = one command + response
- the first word of the write is a constant (0x0002 on V1) - the header
- the second word is the opcode, the rest are parameters
- the response's third word is the board state (0x0220 idle / 0x0224 busy)

Cross-check your opcode guesses against an open-source library that already
speaks the same protocol family. `galvoplotter/balormk` documents the JCZ
"balor" command set - the opcodes matched 1:1, which is how the names in
`PROTOCOL.md` are known instead of just numbers.

## Step 4: verify each guess on hardware

A capture tells you what the vendor does, not what the board *requires*.
The final step is the verification loop in `tests/`:

1. write a probe that sends one candidate command and reads the response
2. run it on the real board, check the board's actual behavior
3. for list records: queue a minimal list containing only that record,
   execute it, observe the galvo/laser
4. keep the probes as tests - `tests/test_capabilities.py` is exactly this,
   still runnable as regression

This is what the live probes caught that a capture alone can't show:
the chunk-ack desync, the 2-byte progress handshake before chunk writes,
and the 0x8000 mark flag requirement.

## Step 5: record it

Write down what you learned *while you verify it*. The `docs/PROTOCOL.md`
reference is deliberately conservative: every entry is either observed in a
capture **and** confirmed live, or explicitly marked unverified (e.g. the
cor-file upload format).

## Applying this to another board

The method is board-agnostic:

1. capture the vendor software doing its thing (simple, distinct jobs)
2. identify endpoints and packet shapes by repetition
3. match opcodes against open-source protocol libraries for that vendor
4. verify every guess with a live probe on the board
5. document only what survived step 4

If you find a better capture, or verify something marked
unverified (the 0x0015 cor-table payload is known to be missing),
please open an issue or PR - the whole point of documenting this is that
the knowledge outlives the hardware.
