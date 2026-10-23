"""Runtime diagnostics: measure the AI loop's frame-to-frame interval (dt)
under three camera/web configurations, to test whether opening the web
RGB565 channel and/or actively JPEG-encoding for a browser client degrades
the AI loop's effective sampling rate -- the suspected root cause of the
Wi-Fi mouse-control quality regression reported 2026-10-23 (see
docs/WORK_TRACKER.md). Does not touch any firmware/ file; imports the real
CameraRig/HandTracker/WebState classes from smart_glass_server.py so this
measures the actual production code path, not a reimplementation of the
gesture logic (which this script never calls at all -- only frame timing
is measured here).

Deploy target: /sdcard/runtime_diagnostics/ (kept separate from
/sdcard/smart_glass/, same convention as diag_stage4/diag_stage5).

Edit MODE below and redeploy between runs:
  "2ch_no_web"        -- channel 0 (display) + channel 2 (AI) only, no web
                          channel at all. Matches main.py's camera config.
  "3ch_web_idle"       -- adds channel 1 (web RGB565) and starts the HTTP
                          server, but no client ever connects to /stream.
  "3ch_web_streaming"  -- same as above, but expects a real client pulling
                          /stream concurrently (e.g. `curl .../stream -o
                          /dev/null` from the Mac) so JPEG encoding actually
                          runs every stream cycle.
"""

import sys
import time
import gc

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import smart_glass_server as sgs

MODE = "3ch_web_streaming"

ENABLE_WEB = MODE != "2ch_no_web"
sgs.config.VERBOSE_ORCHESTRATOR_LOGS = (MODE == "3ch_web_streaming")

FRAME_TARGET = 60


def run():
    rig = sgs.CameraRig()
    rig.create(
        enable_display=True,
        enable_ai=True,
        enable_web=ENABLE_WEB,
        ai_size=sgs.AI_RGB888P_SIZE,
        web_size=[sgs.WEB_FRAME_WIDTH, sgs.WEB_FRAME_HEIGHT],
        display_mode=sgs.DISPLAY_MODE,
    )
    tracker = sgs.HandTracker(
        "/sdcard/examples/kmodel/hand_det.kmodel",
        "/sdcard/examples/kmodel/handkp_det.kmodel",
        sgs.AI_RGB888P_SIZE,
    )
    web_state = None
    if ENABLE_WEB:
        # Connect Wi-Fi inside this same script run (not via a separate
        # prior run_script call) -- canmv_execute_file does its own soft
        # reboot before running, which resets the socket layer even if
        # wlan.isconnected() still reads True from before, reproducing the
        # documented "no available NIC" race. Doing it here, in the same
        # uninterrupted run as the actual HttpServer.start(), matches how
        # run_wifi.py/smart_glass_server.main() actually does it and avoids
        # that race.
        import wifi
        import wifi_credentials
        wlan, ifconfig, ssid = wifi.connect_if_needed(
            [
                (wifi_credentials.HOME_SSID, wifi_credentials.HOME_PASSWORD),
                (wifi_credentials.HOTSPOT_SSID, wifi_credentials.HOTSPOT_PASSWORD),
            ],
            on_progress=print,
        )
        print("[DIAG] wifi ready", ifconfig, ssid)
        web_state = sgs.WebState()
        web_state.start(sgs.WEB_PORT)
        print("[DIAG] web started on port", sgs.WEB_PORT, "mode=", MODE)
    else:
        print("[DIAG] web disabled, mode=", MODE)

    intervals = []
    last_ms = None
    frame_count = 0
    try:
        while frame_count < FRAME_TARGET:
            frame_count += 1
            now = time.ticks_ms()
            if last_ms is not None:
                intervals.append(time.ticks_diff(now, last_ms))
            last_ms = now

            ai_frame = rig.get_ai_frame()
            tracker.run(ai_frame)
            rig.osd_img.clear()
            rig.refresh_osd()

            if web_state is not None:
                web_state.step(rig, None)

            if frame_count % 50 == 0:
                gc.collect()
                print("[DIAG] frame", frame_count, "mem_free", gc.mem_free())
    finally:
        if intervals:
            s = sorted(intervals)
            n = len(s)
            avg = sum(s) / n
            p50 = s[n // 2]
            p95 = s[int(n * 0.95)]
            worst = s[-1]
            over90 = sum(1 for d in intervals if d > 90)
            over180 = sum(1 for d in intervals if d > 180)
            over350 = sum(1 for d in intervals if d > 350)
            fps = 1000.0 / avg if avg > 0 else 0.0
            print("[DIAG] RESULT mode=%s n=%d avg_ms=%.1f fps=%.1f p50_ms=%d p95_ms=%d max_ms=%d over90ms=%d over180ms=%d over350ms=%d" % (
                MODE, n, avg, fps, p50, p95, worst, over90, over180, over350))
        if web_state is not None and web_state.server is not None:
            web_state.server.close()
        rig.destroy()
        print("[DIAG] done")


if __name__ == "__main__":
    run()
