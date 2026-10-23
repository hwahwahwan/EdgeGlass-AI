"""Runtime diagnostics: separate JPEG-encode (CPU) cost from Wi-Fi network
send cost while a real /stream client is connected, and compare the AI
loop's frame-to-frame interval (dt) with WebState.frame_interval_ms
throttled (200ms, the deployed fix) vs disabled (0ms, pre-fix behavior) --
same board, same code, same session, so the before/after comparison is a
real measurement rather than a historical guess. See docs/WORK_TRACKER.md
section M and docs/DEV_HISTORY.md problem #20/#9 for why this split
matters: an old hotspot measurement (#9) found MJPEG throughput as low as
~640 B/s, so a frame-timing stall could be network-bound (slow send()),
not CPU-bound (img.compress()) -- this script measures both directly
instead of assuming either.

Does NOT modify firmware/smart_glass_server.py, firmware/web_server.py, or
firmware/video_stream.py -- it monkey-patches video_stream.encode_jpeg and
web_server.ClientSession.queue/pump_send at runtime, in this throwaway
process only, purely to time them. Never touches gesture_controller.py,
mouse_controller.py, or hand_tracker.py, and never calls the gesture logic
at all (hand_result is always None) -- this measures AI-loop timing only.

Deploy target: /sdcard/runtime_diagnostics/.

Edit THROTTLE_MS below and redeploy between the two comparison runs:
  0    -- disables the throttle (WebState.frame_interval_ms forced to 0),
          approximating pre-fix behavior for comparison.
  200  -- matches the currently deployed WEB_STREAM_MIN_INTERVAL_MS default.

Run with a real client pulling /stream concurrently, e.g.:
  curl --max-time 30 http://<board-ip>:8060/stream -o /dev/null
"""

import sys
import time
import gc

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import smart_glass_server as sgs
import web_server
import video_stream

THROTTLE_MS = 0

FRAME_TARGET = 80

# ---- instrumentation: wrap, don't modify, the real functions/methods ----
encode_events = []   # (started_at_ms, duration_ms, failed)
send_events = []     # (queued_at_ms, done_at_ms, duration_ms, byte_len)

_orig_encode_jpeg = video_stream.encode_jpeg


def _timed_encode_jpeg(img, quality=50):
    t0 = time.ticks_ms()
    try:
        data, encode_ms = _orig_encode_jpeg(img, quality=quality)
        encode_events.append((t0, time.ticks_diff(time.ticks_ms(), t0), False))
        return data, encode_ms
    except OSError:
        encode_events.append((t0, time.ticks_diff(time.ticks_ms(), t0), True))
        raise


video_stream.encode_jpeg = _timed_encode_jpeg

_orig_queue = web_server.ClientSession.queue
_orig_pump_send = web_server.ClientSession.pump_send
_queue_started = {}


def _timed_queue(self, data):
    _queue_started[id(self)] = (time.ticks_ms(), len(data))
    return _orig_queue(self, data)


def _timed_pump_send(self):
    done = _orig_pump_send(self)
    if done:
        start = _queue_started.pop(id(self), None)
        if start is not None:
            t0, nbytes = start
            send_events.append((t0, time.ticks_diff(time.ticks_ms(), t0), nbytes))
    return done


web_server.ClientSession.queue = _timed_queue
web_server.ClientSession.pump_send = _timed_pump_send


def _stats(label, values):
    if not values:
        print("[DIAG] %s: no samples" % label)
        return
    s = sorted(values)
    n = len(s)
    avg = sum(s) / n
    p50 = s[n // 2]
    p95 = s[int(n * 0.95)] if n > 1 else s[0]
    print("[DIAG] %s n=%d avg=%.1f p50=%d p95=%d max=%d min=%d" % (
        label, n, avg, p50, p95, s[-1], s[0]))


def run():
    rig = sgs.CameraRig()
    rig.create(
        enable_display=True,
        enable_ai=True,
        enable_web=True,
        ai_size=sgs.AI_RGB888P_SIZE,
        web_size=[sgs.WEB_FRAME_WIDTH, sgs.WEB_FRAME_HEIGHT],
        display_mode=sgs.DISPLAY_MODE,
    )
    tracker = sgs.HandTracker(
        "/sdcard/examples/kmodel/hand_det.kmodel",
        "/sdcard/examples/kmodel/handkp_det.kmodel",
        sgs.AI_RGB888P_SIZE,
    )

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
    web_state.frame_interval_ms = THROTTLE_MS
    web_state.start(sgs.WEB_PORT)
    print("[DIAG] web started on port", sgs.WEB_PORT, "THROTTLE_MS=", THROTTLE_MS)

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

            web_state.step(rig, None)

            if frame_count % 25 == 0:
                gc.collect()
                print("[DIAG] frame", frame_count, "mem_free", gc.mem_free())
    finally:
        print("[DIAG] ===== RESULTS (THROTTLE_MS=%d) =====" % THROTTLE_MS)
        _stats("ai_loop_dt_ms", intervals)
        if intervals:
            over90 = sum(1 for d in intervals if d > 90)
            over180 = sum(1 for d in intervals if d > 180)
            over350 = sum(1 for d in intervals if d > 350)
            print("[DIAG] ai_loop_dt over90ms=%d over180ms=%d over350ms=%d of n=%d" % (
                over90, over180, over350, len(intervals)))
        encode_durations = [d for (_, d, failed) in encode_events if not failed]
        encode_failures = sum(1 for (_, _, failed) in encode_events if failed)
        _stats("jpeg_encode_ms (CPU-bound)", encode_durations)
        print("[DIAG] jpeg_encode_failures=%d of %d attempts" % (encode_failures, len(encode_events)))
        send_durations = [d for (_, d, _) in send_events]
        _stats("network_send_ms (network-bound)", send_durations)
        if send_events:
            total_bytes = sum(nb for (_, _, nb) in send_events)
            total_send_ms = sum(d for (_, d, _) in send_events)
            if total_send_ms > 0:
                print("[DIAG] approx_throughput_bytes_per_sec=%.1f (total_bytes=%d over total_send_ms=%d)" % (
                    total_bytes * 1000.0 / total_send_ms, total_bytes, total_send_ms))
        web_state.server.close()
        rig.destroy()
        print("[DIAG] done")


if __name__ == "__main__":
    run()
