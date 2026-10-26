"""EdgeGlass-AI standalone auto-boot entry point -- deploys to /sdcard/main.py.

Runs automatically on every power-up (standard MicroPython boot.py ->
main.py sequence, see tools/autorun/boot.py), WITHOUT needing a USB data
connection, launching the exact profile firmware/run_wifi.py pins:
camera + AI (HandTracker) + OLED skeleton + Wi-Fi + UDP mouse control
(auto-discovery, registers with mac/mac_mouse_bridge.py listening on UDP
9000) + web server (/snapshot, /stream), via firmware/smart_glass_server.py
(transport_kind="udp", enable_web=True). Switched from UART to UDP
2026-10-26 (docs/DEV_HISTORY.md 4-3) -- UART requires a physical
UART2/CH342K cable to the Mac, which defeats the point of a power-only
standalone boot; UDP lets the Mac bridge find the board wirelessly over
whatever Wi-Fi network it's on. This does NOT replace
firmware/run_uart.py (left exactly as-is, still USB/UART-only, no web --
see its own docstring) / run_wifi.py / run_uart_web.py -- those still
exist under /sdcard/smart_glass/ for manual USB/REPL runs; this file is
only the thing that gets the UDP+web profile running when nobody is there
to press "run" in the IDE.

This is NOT firmware/main.py (the separate, preserved hand-tracking-only
script deployed to /sdcard/smart_glass/main.py) -- /sdcard/main.py is a
board-root-level file with special MicroPython boot semantics, a
different file entirely. Do not confuse the two.

=== RECOVERY: two independent ways to skip auto-launch ===

This combination (camera + AI + OLED + Wi-Fi + UDP mouse + web, all at
once) had real documented failures in earlier sessions on this exact
codebase (tools/DEPLOY.md: "HttpServer: bind failed after 20 retries",
and a separate MediaManager/Display misconfiguration that hung the board
hard enough to need a physical power cycle) -- and the UDP mouse path
specifically is the less-tested of the two transports (confirmed working
manually on 2026-10-26, but with far fewer total runs than UART). Both
recovery paths below exist *because* of that history, not as generic
boilerplate:

  1. USB REPL interrupt: connect over USB during the countdown printed
     below and send a serial break / Ctrl-C (the CanMV IDE's Stop button
     does this, so does canmv_stop_script() over the MCP tools) before it
     reaches zero. MicroPython drops to the >>> REPL immediately and never
     proceeds to the launch below -- manual control still works exactly
     as it always has, e.g. running firmware/run_uart.py by hand instead.
  2. Safe-mode flag file: if /sdcard/SAFE_MODE exists, auto-launch is
     skipped unconditionally -- checked before the countdown even starts.
     Create this file to recover WITHOUT needing to time a USB interrupt
     (e.g. write it via the IDE/MCP tools if USB/REPL is still reachable,
     or pull the SD card and create it from a PC if it is not).

What neither of these can protect against is a genuine hardware/firmware
-level hang (the MediaManager/Display case above, or a camera/Wi-Fi
driver lockup) -- that is not a Python exception, so no amount of
try/except here catches it; it needs a physical power cycle regardless.
A plain Python exception (Wi-Fi not in range and connect_if_needed()
raising OSError, a missing kmodel, etc.) is already safe without any of
this: MicroPython just prints the traceback and drops to the REPL, it
does not retry or reboot-loop on its own.
"""

import sys
import time

try:
    with open("/sdcard/SAFE_MODE"):
        pass
    print("[BOOT] /sdcard/SAFE_MODE present -- skipping auto-launch, REPL only")
except OSError:
    print("[BOOT] EdgeGlass-AI auto-launch in 8s.")
    print("[BOOT] To cancel: connect over USB and interrupt now (IDE Stop")
    print("[BOOT] button / Ctrl-C / canmv_stop_script) for a REPL instead,")
    print("[BOOT] or create /sdcard/SAFE_MODE before the next power-up.")
    for remaining in (8, 7, 6, 5, 4, 3, 2, 1):
        print("[BOOT] launching in %d..." % remaining)
        time.sleep(1)

    print("[BOOT] launching firmware/run_wifi.py profile "
          "(camera+AI+OLED+Wi-Fi+UDP mouse+web)")
    PROJECT_DIR = "/sdcard/smart_glass"
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    try:
        import smart_glass_server
        smart_glass_server.main(transport_kind="udp", enable_web=True)
    except Exception as error:
        # Any plain exception here is already safe (MicroPython drops to
        # the REPL on an unhandled exception in main.py, no reboot loop) --
        # this except just makes the recovery message explicit instead of
        # leaving only a bare traceback.
        print("[BOOT] launch failed, dropping to REPL:", repr(error))
        print("[BOOT] run firmware/run_uart.py by hand instead, or fix and")
        print("[BOOT] re-deploy, or create /sdcard/SAFE_MODE and reset.")
        raise
