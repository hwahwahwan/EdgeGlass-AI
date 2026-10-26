"""Pure-Python hand-landmark -> OLED-skeleton geometry.

No machine/framebuf/I2C import here at all -- this module is plain data
transformation (landmarks in, pixel points/lines out) so it is directly
unit-testable on a PC with no mocks (see display/tests/test_hand_renderer.py,
which imports this firmware/ module directly).

Reuses the EXACT 21-point index layout and skeleton connection list
already used by firmware/ui.py's draw_landmarks() (wrist=0, thumb=1-4,
index=5-8, middle=9-12, ring=13-16, pinky=17-20; no palm-arc connections --
firmware/ui.py doesn't draw those either, so this mirrors it rather than
inventing a different topology). The list is duplicated here, not
imported from ui.py, to keep this module's only dependency being its own
input data (see display/DEVELOPMENT.md "기존 코드 참조 여부" for the
original design rationale, from when this lived in display/src/).
"""

NUM_LANDMARKS = 21

# Identical to firmware/ui.py's _SKELETON_CONNECTIONS.
SKELETON_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
]


def landmarks_bounds(landmarks):
    """Return (min_x, min_y, max_x, max_y) over all 21 (x, y) pairs, or
    None if ``landmarks`` is falsy, too short, or contains a malformed
    entry (not an (x, y) pair of numbers)."""
    if not landmarks:
        return None
    xs = []
    ys = []
    for i in range(NUM_LANDMARKS):
        try:
            x, y = landmarks[i]
            x = float(x)
            y = float(y)
        except (IndexError, TypeError, ValueError):
            return None
        xs.append(x)
        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def layout_skeleton(landmarks, area_width, area_height, margin=2):
    """Map 21 (x, y) landmark pairs, in any consistent input coordinate
    space (this project's firmware hands them over in AI_RGB888P_SIZE
    pixel space -- see config.AI_FRAME_WIDTH/HEIGHT -- but this function
    only ever looks at their positions *relative to each other*), into
    integer pixel positions inside a (area_width x area_height) box.

    - Preserves the hand's aspect ratio (uniform scale, fits the longer
      axis) instead of stretching it to fill the box.
    - Centers the scaled hand in the box.
    - Clamps every point to stay inside [0, area_width) x [0, area_height),
      so nothing is ever drawn outside the given area even for landmarks
      slightly out of the source frame.
    - Degenerate input (a single point, or all landmarks at the same
      spot) does not divide by zero -- span is floored to a small epsilon.

    Returns (points, lines):
      points -- list of exactly 21 (px, py) int tuples, or None entries
                for landmarks layout_skeleton could not place (currently
                only happens if landmarks itself was malformed, in which
                case every entry is None).
      lines  -- list of ((ax, ay), (bx, by)) int-tuple pairs, one per
                SKELETON_CONNECTIONS entry whose both endpoints are
                non-None.

    Returns ([None] * 21, []) if landmarks_bounds(landmarks) is None (no
    hand / bad data) -- callers should treat that as "draw nothing".
    """
    bounds = landmarks_bounds(landmarks)
    if bounds is None:
        return [None] * NUM_LANDMARKS, []
    min_x, min_y, max_x, max_y = bounds
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)

    usable_w = max(area_width - 2 * margin, 1)
    usable_h = max(area_height - 2 * margin, 1)

    scale = min(usable_w / span_x, usable_h / span_y)
    draw_w = span_x * scale
    draw_h = span_y * scale
    offset_x = margin + (usable_w - draw_w) / 2.0
    offset_y = margin + (usable_h - draw_h) / 2.0

    def _map(i):
        x, y = landmarks[i]
        px = int(round(offset_x + (float(x) - min_x) * scale))
        py = int(round(offset_y + (float(y) - min_y) * scale))
        px = max(0, min(area_width - 1, px))
        py = max(0, min(area_height - 1, py))
        return px, py

    points = [_map(i) for i in range(NUM_LANDMARKS)]
    lines = [
        (points[a], points[b])
        for a, b in SKELETON_CONNECTIONS
    ]
    return points, lines
