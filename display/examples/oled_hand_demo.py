"""Board-only real-panel demo: drives DisplayUI with synthetic 21-point
hand landmarks on the actual VLT-OL016 OLED (not the PC VirtualOLED used
by examples/hand_demo.py). This is the first script that exercises the
skeleton-rendering code path (hand_renderer + DisplayUI) on real hardware,
as opposed to oled_basic_test.py which only exercises fill/text/rect.

Not wired up to firmware/'s real hand_tracker.py yet -- this uses the same
hand-shaped synthetic landmark generators as examples/hand_demo.py
(duplicated here, not imported, since this file is deployed flat to
/sdcard/display/ and hand_demo.py depends on Pillow/VirtualOLED which
don't exist on the board) so the skeleton layout/joint-dot/status-bar code
can be checked on the real panel before the real AI loop is connected (see
docs/DEV_HISTORY.md 4-3 for the connection-point analysis).

Deploy flattened next to the other display/ files (see README.md "보드에서
실행할 테스트 파일"), e.g. to /sdcard/display/, then run this file directly
from the CanMV IDE. Runs forever, cycling through open hand -> closing ->
fist -> opening -> no-hand, printing which pose is showing each frame;
stop from the IDE when done watching.
"""

import sys
import time

PROJECT_DIR = "/sdcard/display"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import oled_device
import display_ui

FRAME_DELAY_MS = 900


def _open_hand(wrist=(320, 260)):
    wx, wy = wrist
    offsets = [
        (0, 0),
        (-18, -6), (-34, -14), (-46, -20), (-56, -24),
        (-16, -30), (-22, -52), (-26, -68), (-30, -80),
        (0, -32), (0, -58), (0, -74), (0, -86),
        (16, -30), (20, -52), (24, -68), (28, -80),
        (30, -22), (40, -36), (46, -48), (50, -56),
    ]
    return [(wx + dx, wy + dy) for dx, dy in offsets]


def _fist_hand(wrist=(320, 260)):
    wx, wy = wrist
    offsets = [
        (0, 0),
        (-13, -5), (-20, -9), (-14, -7), (-6, -4),
        (-17, -30), (-13, -20), (-6, -11), (0, -4),
        (-3, -32), (-1, -21), (1, -11), (2, -4),
        (11, -30), (8, -20), (4, -11), (1, -4),
        (22, -24), (17, -16), (8, -9), (3, -3),
    ]
    return [(wx + dx, wy + dy) for dx, dy in offsets]


def _lerp_hands(a, b, t):
    return [(ax + (bx - ax) * t, ay + (by - ay) * t) for (ax, ay), (bx, by) in zip(a, b)]


def _build_sequence():
    """A looping list of (name, landmarks, gesture, fps) frames: open hand
    holds, closes to a fist over a few frames, holds as a fist, opens back
    up, then a no-hand frame -- so all of layout_skeleton()'s code paths
    (normal hand, degenerate/no-hand) get exercised on the real panel."""
    open_h = _open_hand()
    fist_h = _fist_hand()
    seq = []
    seq.append(("open_hand (MOVE)", open_h, "MOVE", 8.5))
    seq.append(("open_hand (MOVE)", open_h, "MOVE", 8.5))
    for t in (0.25, 0.5, 0.75):
        seq.append(("closing t=%.2f (MOVE)" % t, _lerp_hands(open_h, fist_h, t), "MOVE", 8.3))
    seq.append(("fist (DRAG)", fist_h, "DRAG", 7.9))
    seq.append(("fist (DRAG)", fist_h, "DRAG", 7.9))
    for t in (0.75, 0.5, 0.25):
        seq.append(("opening t=%.2f (MOVE)" % t, _lerp_hands(open_h, fist_h, t), "MOVE", 8.3))
    seq.append(("no_hand (STOP)", None, "STOP", None))
    return seq


def main():
    print("oled_hand_demo: starting -- make sure the panel is wired and powered")
    oled = oled_device.open_display()
    if oled is None:
        print("oled_hand_demo: FAILED -- open_display() returned None, see [OLED] log above")
        return

    ui = display_ui.DisplayUI(oled)
    sequence = _build_sequence()
    print("oled_hand_demo: cycling %d frames forever, ~%dms apart -- stop from the IDE when done"
          % (len(sequence), FRAME_DELAY_MS))

    cycle = 0
    try:
        while True:
            cycle += 1
            for name, landmarks, gesture, fps in sequence:
                print("oled_hand_demo: cycle %d -- showing: %s" % (cycle, name))
                ui.update(landmarks, gesture, fps=fps, force=True)
                time.sleep_ms(FRAME_DELAY_MS)
    finally:
        oled_device.close_display(oled)


if __name__ == "__main__":
    main()
