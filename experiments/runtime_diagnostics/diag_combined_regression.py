"""Combined diagnostics (2026-10-23): run the REAL production entry point
(smart_glass_server.main(transport_kind="udp", enable_web=True), i.e. what
run_wifi.py calls) with timing instrumentation, in one single real-hardware
session, for two purposes at once:

  1. Performance regression check for the WEB_STREAM_MIN_INTERVAL_MS=200
     throttle fix (docs/WORK_TRACKER.md section M, docs/DEV_HISTORY.md
     problem #20): AI-loop frame dt, JPEG-encode (CPU) time, and network
     send time, measured SEPARATELY so a stall can be attributed correctly
     instead of assumed (problem #9's old hotspot-MJPEG-throughput finding
     means network delay is a real alternative explanation).
  2. Unexplained-termination tracking: client connect/disconnect, socket
     exceptions, JPEG failures, memory snapshots, and -- most importantly
     -- a clear distinction at the end between a deliberate stop (IDE
     interrupt, i.e. this script being stopped on purpose) and any other
     unexpected exception.

This reuses 100% of the real Wi-Fi auto-connect (wifi.py) and UDP
auto-discovery (discovery.py/transport.py) code paths -- nothing here
re-implements or changes gesture_controller.py, mouse_controller.py,
hand_tracker.py, wifi.py, or discovery.py. All instrumentation is done by
monkey-patching video_stream.encode_jpeg and web_server.ClientSession
methods at runtime, in this throwaway process only; the real files on disk
are never touched.

THROTTLE_MS below overrides WebState.frame_interval_ms for this run only
(the real deployed default, read from smart_glass_server.WEB_STREAM_MIN_INTERVAL_MS,
is left untouched on disk). Edit and redeploy to compare:
  200 -- matches the currently deployed fix.
  0   -- disables the throttle, approximating pre-fix behavior.

Deploy target: /sdcard/runtime_diagnostics/.
Stop this script (canmv_stop_script) to end the observation window and see
the final [DIAG] RUN SUMMARY -- that stop will show up in the log as
"IDE interrupt", distinguishing it from a real crash.
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

THROTTLE_MS = 200

sgs.config.VERBOSE_ORCHESTRATOR_LOGS = True

RUN_START_MS = time.ticks_ms()
print("[DIAG] RUN_START ms=%d THROTTLE_MS=%d mem_free=%d" % (
    RUN_START_MS, THROTTLE_MS, gc.mem_free()))

# ---- instrumentation: wrap, don't modify, the real functions/methods ----
encode_events = []   # (started_at_ms, duration_ms, failed)
send_events = []     # (queued_at_ms, duration_ms, byte_len)
client_events = []   # (ts_ms, "connect"/"disconnect", addr)

_orig_encode_jpeg = video_stream.encode_jpeg


def _timed_encode_jpeg(img, quality=50):
    t0 = time.ticks_ms()
    try:
        data, encode_ms = _orig_encode_jpeg(img, quality=quality)
        encode_events.append((t0, time.ticks_diff(time.ticks_ms(), t0), False))
        return data, encode_ms
    except OSError as e:
        encode_events.append((t0, time.ticks_diff(time.ticks_ms(), t0), True))
        print("[DIAG] JPEG_ENCODE_FAIL at ms=%d err=%r mem_free=%d" % (t0, e, gc.mem_free()))
        raise


video_stream.encode_jpeg = _timed_encode_jpeg

_orig_queue = web_server.ClientSession.queue
_orig_pump_send = web_server.ClientSession.pump_send
_orig_close = web_server.ClientSession.close
_orig_init = web_server.ClientSession.__init__
_queue_started = {}


def _timed_init(self, sock, addr, *a, **kw):
    client_events.append((time.ticks_ms(), "connect", addr))
    print("[DIAG] CLIENT_CONNECT addr=%r mem_free=%d" % (addr, gc.mem_free()))
    return _orig_init(self, sock, addr, *a, **kw)


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


def _timed_close(self):
    client_events.append((time.ticks_ms(), "disconnect", self.addr))
    print("[DIAG] CLIENT_DISCONNECT addr=%r mem_free=%d" % (self.addr, gc.mem_free()))
    return _orig_close(self)


web_server.ClientSession.__init__ = _timed_init
web_server.ClientSession.queue = _timed_queue
web_server.ClientSession.pump_send = _timed_pump_send
web_server.ClientSession.close = _timed_close

_orig_webstate_init = sgs.WebState.__init__


def _patched_webstate_init(self):
    _orig_webstate_init(self)
    self.frame_interval_ms = THROTTLE_MS


sgs.WebState.__init__ = _patched_webstate_init

exit_kind = [None]
exit_detail = [None]

try:
    sgs.main(transport_kind="udp", enable_web=True)
    exit_kind[0] = "returned_normally"
except KeyboardInterrupt as e:
    exit_kind[0] = "deliberate_stop"
    exit_detail[0] = repr(e)
except BaseException as e:
    msg = str(e)
    if "IDE interrupt" in msg:
        exit_kind[0] = "deliberate_stop"
    else:
        exit_kind[0] = "exception"
    exit_detail[0] = repr(e)
finally:
    run_end_ms = time.ticks_ms()
    uptime_ms = time.ticks_diff(run_end_ms, RUN_START_MS)
    print("[DIAG] ===== RUN SUMMARY (THROTTLE_MS=%d) =====" % THROTTLE_MS)
    print("[DIAG] exit_kind=%s detail=%s uptime_ms=%d mem_free=%d" % (
        exit_kind[0], exit_detail[0], uptime_ms, gc.mem_free()))
    print("[DIAG] client_events=%r" % (client_events,))

    encode_durations = [d for (_, d, failed) in encode_events if not failed]
    encode_failures = sum(1 for (_, _, failed) in encode_events if failed)
    if encode_durations:
        s = sorted(encode_durations)
        n = len(s)
        print("[DIAG] jpeg_encode_ms(CPU) n=%d avg=%.1f p50=%d p95=%d max=%d" % (
            n, sum(s) / n, s[n // 2], s[int(n * 0.95)] if n > 1 else s[0], s[-1]))
    else:
        print("[DIAG] jpeg_encode_ms(CPU): no successful samples")
    print("[DIAG] jpeg_encode_failures=%d of %d attempts" % (encode_failures, len(encode_events)))

    send_durations = [d for (_, d, _) in send_events]
    if send_durations:
        s = sorted(send_durations)
        n = len(s)
        print("[DIAG] network_send_ms n=%d avg=%.1f p50=%d p95=%d max=%d" % (
            n, sum(s) / n, s[n // 2], s[int(n * 0.95)] if n > 1 else s[0], s[-1]))
        total_bytes = sum(nb for (_, _, nb) in send_events)
        total_send_ms = sum(d for (_, d, _) in send_events)
        if total_send_ms > 0:
            print("[DIAG] approx_throughput_bytes_per_sec=%.1f (total_bytes=%d total_send_ms=%d)" % (
                total_bytes * 1000.0 / total_send_ms, total_bytes, total_send_ms))
    else:
        print("[DIAG] network_send_ms: no samples (no client ever finished a /stream frame)")
    print("[DIAG] done")
