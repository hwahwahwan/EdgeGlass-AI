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

=== OLED-first boot (2026-10-30, docs/DEV_HISTORY.md 4-8) ===

The OLED is brought up HERE, before even the SAFE_MODE check, so the
boot-stage screen sequence ("EDGEGLASS-AI/BOOTING", then "SAFE
MODE/START IN Ns...") is visible from the very start -- previously OLED
only came up much later, inside smart_glass_server.main(), well after
this file's countdown had already finished. This intentionally departs
from boot.py's "no camera/AI/Wi-Fi/OLED in the earliest boot stage"
philosophy for OLED specifically, because:
  - oled_device.open_display() is designed to never raise (returns None
    on any failure -- I2C bring-up, no panel at the expected address,
    driver import failure, etc.), so adding it here does not introduce a
    new way for this "must not crash" stage to crash.
  - OLED is an independent I2C resource (display_config.py's I2C_ID/
    PIN_SCL/PIN_SDA) with no pin or bus overlap with the camera, Wi-Fi, or
    AI model loading that happen later -- confirmed by a project-wide
    search, see firmware/display_config.py's own comment.
The already-built ``oled``/``oled_ui`` are then handed into
smart_glass_server.main() instead of letting it open I2C a second time
(see that function's own oled/oled_ui parameters).

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

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# OLED 모듈을 가장 먼저 가져온다 -- SAFE_MODE 체크보다도 먼저 화면을
# 켜기 위해 sys.path 설정도 여기(모듈 최상단)로 옮겨졌다(기존에는 아래
# try/except의 else 분기 안에서만 설정됐었다). import 실패(이 SD카드에
# OLED 모듈이 배포되지 않은 경우)는 여기서 가드해 이 "크래시하면 안
# 되는" 구간의 안전성을 그대로 유지한다.
try:
    import oled_device
    import display_ui
except ImportError:
    oled_device = None
    display_ui = None


def _open_oled():
    """oled_device.open_display()는 어떤 실패에도 예외를 던지지 않고
    None을 반환하도록 설계되어 있다(기존 docstring 참고) -- 여기서도
    그 보장을 그대로 믿고 추가 try/except 없이 호출한다."""
    if oled_device is None or display_ui is None:
        return None, None
    oled = oled_device.open_display()
    if oled is None:
        return None, None
    return oled, display_ui.DisplayUI(oled)


def run_boot(sleep_fn=None, countdown=(8, 7, 6, 5, 4, 3, 2, 1),
             safe_mode_path="/sdcard/SAFE_MODE", launch=None):
    """실제 부팅 시퀀스. 모듈 최상위에서 바로 실행하지 않고 함수로 뺀
    이유는 테스트 가능성이다(tests/test_autorun_main.py) -- 기본
    인자(``sleep_fn=None`` -> ``time.sleep``, 8초 카운트다운, 실제
    SAFE_MODE 경로, 실제 ``smart_glass_server.main()`` 호출)는 실제
    보드 동작을 한 글자도 바꾸지 않고 그대로 재현한다. 테스트는 가짜
    sleep_fn(실제로 안 기다림)과 가짜 launch(미디어 모듈을 임포트하지
    않음 -- smart_glass_server.py는 보드 밖에서 임포트가 원천적으로
    안 됨, docs/DEV_HISTORY.md 참고)를 주입해 8초를 기다리지 않고
    순서/문구/SAFE_MODE 분기만 검증한다.
    """
    sleep_fn = sleep_fn or time.sleep
    oled, oled_ui = _open_oled()
    if oled_ui is not None:
        oled_ui.show_stage(("EDGEGLASS-AI", "BOOTING"))

    try:
        with open(safe_mode_path):
            pass
        print("[BOOT] %s present -- skipping auto-launch, REPL only" % safe_mode_path)
        if oled_ui is not None:
            oled_ui.show_stage(("SAFE MODE", "REPL ONLY"))
        return
    except OSError:
        pass

    print("[BOOT] EdgeGlass-AI auto-launch in %ds." % countdown[0])
    print("[BOOT] To cancel: connect over USB and interrupt now (IDE Stop")
    print("[BOOT] button / Ctrl-C / canmv_stop_script) for a REPL instead,")
    print("[BOOT] or create %s before the next power-up." % safe_mode_path)
    for remaining in countdown:
        print("[BOOT] launching in %d..." % remaining)
        if oled_ui is not None:
            oled_ui.show_stage(("SAFE MODE", "START IN %ds" % remaining))
        sleep_fn(1)

    print("[BOOT] launching firmware/run_wifi.py profile "
          "(camera+AI+OLED+Wi-Fi+UDP mouse+web)")

    if launch is None:
        def launch(oled, oled_ui):
            import smart_glass_server
            smart_glass_server.main(transport_kind="udp", enable_web=True,
                                     oled=oled, oled_ui=oled_ui)

    try:
        launch(oled, oled_ui)
    except Exception as error:
        # Any plain exception here is already safe (MicroPython drops to
        # the REPL on an unhandled exception in main.py, no reboot loop) --
        # this except just makes the recovery message explicit instead of
        # leaving only a bare traceback.
        print("[BOOT] launch failed, dropping to REPL:", repr(error))
        print("[BOOT] run firmware/run_uart.py by hand instead, or fix and")
        print("[BOOT] re-deploy, or create %s and reset." % safe_mode_path)
        raise


run_boot()
