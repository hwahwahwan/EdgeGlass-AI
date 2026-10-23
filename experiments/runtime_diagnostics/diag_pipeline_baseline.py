"""Runtime diagnostics: measure frame-to-frame interval using the REAL
libs.PipeLine class that firmware/main.py (the UART path the user says
works well) actually uses, as a true apples-to-apples comparison against
diag_frame_timing.py's CameraRig-based measurement. If this gives the same
~90-100ms/frame figure, the AI inference cost itself (not the Wi-Fi
orchestrator's camera setup) is the baseline, and the regression must be
looked for elsewhere. See docs/WORK_TRACKER.md 2026-10-23 gesture-quality
regression entry.

Deploy target: /sdcard/runtime_diagnostics/.
"""

import sys
import time
import gc

from libs.PipeLine import PipeLine

PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from hand_tracker import HandTracker

FRAME_TARGET = 100


def run():
    pl = PipeLine(rgb888p_size=[640, 360], display_mode="auto", display_size=None)
    pl.create()
    print("[DIAG] PipeLine created, display_size=", pl.get_display_size())

    tracker = HandTracker(
        "/sdcard/examples/kmodel/hand_det.kmodel",
        "/sdcard/examples/kmodel/handkp_det.kmodel",
        [640, 360],
    )

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

            img = pl.get_frame()
            tracker.run(img)
            pl.osd_img.clear()
            pl.show_image()

            if frame_count % 25 == 0:
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
            print("[DIAG] RESULT mode=pipeline_baseline n=%d avg_ms=%.1f fps=%.1f p50_ms=%d p95_ms=%d max_ms=%d over90ms=%d over180ms=%d over350ms=%d" % (
                n, avg, fps, p50, p95, worst, over90, over180, over350))
        pl.destroy()
        print("[DIAG] done")


if __name__ == "__main__":
    run()
