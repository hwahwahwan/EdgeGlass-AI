"""PC-only virtual OLED demo -- no CanMV/machine/board required.

Drives firmware/display_ui.py (single source of truth for what's deployed
to the board -- see docs/DEV_HISTORY.md) with synthetic 21-point hand
landmarks through tests/virtual_oled.py's VirtualOLED, and saves a small, deliberately
limited set of pose scenarios (open hand, fist, fingers-closing motion) as
both a scaled-up PNG (6x, for easy viewing) and a true 128x64 native-
resolution PNG (*_native_128x64.png) under display/examples/output/ so
the real on-panel layout and pixel density can be reviewed without the
real VLT-OL016 panel (see README.md "PC에서 가상 화면을 확인하는 방법").
The open-hand pose is additionally rendered at joint_size=2 and
joint_size=3 for a direct dot-size comparison (DEVELOPMENT.md 2-8).

Run:
    cd display && python3 examples/hand_demo.py

Requires Pillow (see requirements.txt) for the PNG export; everything else
(display_ui, hand_renderer, VirtualOLED) is pure Python with no extra
dependency.
"""

import os
import sys

_DISPLAY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIRMWARE_ROOT = os.path.join(os.path.dirname(_DISPLAY_ROOT), "firmware")
for _path in [_FIRMWARE_ROOT, os.path.join(_DISPLAY_ROOT, "tests")]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

import display_ui  # noqa: E402
from virtual_oled import VirtualOLED  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _open_hand(wrist=(320, 260), spread=1.0):
    """21 synthetic landmarks shaped like an open hand with spread
    fingers, in AI_RGB888P_SIZE-like pixel space (roughly 640x360) so this
    exercises the same coordinate range the real hand_tracker.py would
    hand over.

    Widened (fingers angled outward, thumb/pinky splayed further sideways)
    compared to the original straight-up-fingers version: that version's
    bounding box was tall and narrow (width:height ~= 0.6), which on the
    landscape 128x54 skeleton area (width:height ~= 2.5) left most of the
    width unused after layout_skeleton()'s aspect-preserving fit -- see
    DEVELOPMENT.md 2-8. This shape (width:height ~= 1.2) roughly doubles
    the rendered hand's on-panel size while still being a plausible
    "fingers spread toward camera" pose, not a stretched/distorted one."""
    wx, wy = wrist
    offsets = [
        (0, 0),
        (-18, -6), (-34, -14), (-46, -20), (-56, -24),
        (-16, -30), (-22, -52), (-26, -68), (-30, -80),
        (0, -32), (0, -58), (0, -74), (0, -86),
        (16, -30), (20, -52), (24, -68), (28, -80),
        (30, -22), (40, -36), (46, -48), (50, -56),
    ]
    return [(wx + dx * spread, wy + dy * spread) for dx, dy in offsets]


def _fist_hand(wrist=(320, 260)):
    """A closed fist: MCP knuckles form the usual spread-out ridge, but
    each finger folds sharply back so its TIP ends up near the *palm
    center* (small x, small y, close to the wrist) rather than away from
    it -- a distinct compact/hooked silhouette instead of the open hand's
    fan shape, which stays recognizable even after layout_skeleton()'s
    zoom-to-fit (bounding-box) normalization.

    Knuckle x-offsets widened ~1.4x from the original (y unchanged) for
    the same reason as _open_hand(): the original bounding box
    (width:height ~= 0.9) under-used the landscape panel's width. This
    version (~1.3) renders noticeably larger on-panel (see
    DEVELOPMENT.md 2-8)."""
    wx, wy = wrist
    offsets = [
        (0, 0),                                               # 0 wrist
        (-13, -5), (-20, -9), (-14, -7), (-6, -4),             # 1-4 thumb, folded across the palm
        (-17, -30), (-13, -20), (-6, -11), (0, -4),            # 5-8 index: MCP out, TIP folds to palm center
        (-3, -32), (-1, -21), (1, -11), (2, -4),               # 9-12 middle
        (11, -30), (8, -20), (4, -11), (1, -4),                # 13-16 ring
        (22, -24), (17, -16), (8, -9), (3, -3),                # 17-20 pinky
    ]
    # NOTE: hand-tuned synthetic coordinates, not real AI model output --
    # after layout_skeleton()'s zoom-to-fit normalization this reads as
    # "fingers bent back" rather than a tight closed-fist silhouette (see
    # DEVELOPMENT.md). A real fist from the actual hand_tracker.py output
    # will look different; this scenario mainly exercises that a curled,
    # self-crossing topology renders without error, same as the open hand.
    return [(wx + dx, wy + dy) for dx, dy in offsets]


def _lerp_hands(a, b, t):
    return [(ax + (bx - ax) * t, ay + (by - ay) * t) for (ax, ay), (bx, by) in zip(a, b)]


def _save(ui, canvas, name, landmarks, gesture, fps=None):
    ui.update(landmarks, gesture, fps=fps, now_ms=0, force=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name + ".png")
    canvas.to_png(path)
    # Also save the true 128x64 image (scale=1, no upscaling) so the real
    # on-panel pixel density/legibility can be checked, not just the 6x
    # magnified preview.
    native_path = os.path.join(OUTPUT_DIR, name + "_native_128x64.png")
    canvas.to_png(native_path, scale=1)
    print("saved", path, "and", native_path)


def main():
    scenarios = []

    open_hand = _open_hand()
    fist_hand = _fist_hand()
    motion_half_closed = _lerp_hands(open_hand, fist_hand, 0.5)

    # Open hand: rendered at both joint_size=2 (current default) and
    # joint_size=3, side by side, so the dot-size trade-off can be compared
    # directly on the now-larger hand (see DEVELOPMENT.md 2-7/2-8).
    for joint_size in (2, 3):
        canvas = VirtualOLED()
        ui = display_ui.DisplayUI(canvas, joint_size=joint_size)
        name = "01_open_hand_move_joint%d" % joint_size
        _save(ui, canvas, name, open_hand, "MOVE", fps=8.5)
        scenarios.append(name)

    # Fist and "fingers closing" motion: joint_size=2 (the default) only,
    # to confirm the widened hand shape also fills the panel for other
    # poses, not just the open hand.
    canvas = VirtualOLED()
    ui = display_ui.DisplayUI(canvas)
    _save(ui, canvas, "02_fist_drag_joint2", fist_hand, "DRAG", fps=7.9)
    scenarios.append("02_fist_drag_joint2")

    canvas = VirtualOLED()
    ui = display_ui.DisplayUI(canvas)
    _save(ui, canvas, "03_finger_motion_half_closed_joint2", motion_half_closed, "MOVE", fps=8.2)
    scenarios.append("03_finger_motion_half_closed_joint2")

    # Throttle / error-handling smoke checks -- console-only (no PNG), kept
    # so this script still demonstrates DisplayUI.update()'s rate limiting
    # (config.MIN_UPDATE_INTERVAL_MS) and safe-failure behavior without
    # adding to the PNG count above.
    canvas = VirtualOLED()
    ui = display_ui.DisplayUI(canvas, min_interval_ms=100)
    drew_flags = []
    for ms in (0, 10, 20, 30, 150, 160, 300):
        drew_flags.append(ui.update(open_hand, "MOVE", fps=8.5, now_ms=ms))
    print("throttle check: now_ms=[0,10,20,30,150,160,300] drew=%r "
          "(expected [True, False, False, False, True, False, True])" % (drew_flags,))

    ui_no_canvas = display_ui.DisplayUI(canvas=None)
    assert ui_no_canvas.update(open_hand, "MOVE") is False

    class _ExplodingCanvas:
        def fill(self, c):
            raise RuntimeError("simulated I2C failure")

    ui_broken = display_ui.DisplayUI(canvas=_ExplodingCanvas())
    assert ui_broken.update(open_hand, "MOVE") is False
    print("error handling check: None canvas and a raising canvas both handled safely (no exception)")

    print("\nhand_demo: %d PNG scenario(s) written to %s (2 files each: 6x scaled + native 128x64)"
          % (len(scenarios), OUTPUT_DIR))


if __name__ == "__main__":
    main()
