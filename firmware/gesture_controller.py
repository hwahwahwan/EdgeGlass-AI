import math
import time


# ============================================================
# Air-mouse pointer tuning
#
# MOVE filters only the index tip, then moves relative to a stable hand
# reference. The camera position never maps directly to a screen position.
# ============================================================

POINTER_DELTA_GAIN = 1.0
POINTER_DEAD_ZONE = 5.0
POINTER_MIN_CUTOFF = 1.0
POINTER_BETA = 0.05
POINTER_D_CUTOFF = 1.0

DRAG_PALM_ALPHA = 0.45
DRAG_DEAD_ZONE = 3


class OneEuroFilter:
    """One-axis One Euro filter for pixel positions and millisecond ticks."""

    def __init__(self):
        self.value = None
        self.derivative = 0.0
        self.last_ms = None

    def reset(self, value=None, now=None):
        self.value = None if value is None else float(value)
        self.derivative = 0.0
        self.last_ms = now

    def filter(self, value, now):
        value = float(value)
        if self.value is None:
            self.reset(value, now)
            return value

        dt_ms = time.ticks_diff(now, self.last_ms)
        if dt_ms <= 0:
            dt_ms = 1
        dt = dt_ms / 1000.0

        derivative = (value - self.value) / dt
        alpha_d = (2.0 * math.pi * POINTER_D_CUTOFF * dt) / (
            1.0 + 2.0 * math.pi * POINTER_D_CUTOFF * dt
        )
        self.derivative += alpha_d * (derivative - self.derivative)

        cutoff = POINTER_MIN_CUTOFF + POINTER_BETA * abs(self.derivative)
        alpha = (2.0 * math.pi * cutoff * dt) / (
            1.0 + 2.0 * math.pi * cutoff * dt
        )
        self.value += alpha * (value - self.value)
        self.last_ms = now
        return self.value


# ============================================================
# 기본 함수
# ============================================================

def distance_xy(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx * dx + dy * dy)


def vector_angle(v1x, v1y, v2x, v2y):

    n1 = math.sqrt(v1x * v1x + v1y * v1y)
    n2 = math.sqrt(v2x * v2x + v2y * v2y)

    denominator = n1 * n2

    if denominator <= 0.000001:
        return 65535.0

    cos_angle = (
        (v1x * v2x + v1y * v2y)
        /
        denominator
    )

    if cos_angle > 1.0:
        cos_angle = 1.0

    if cos_angle < -1.0:
        cos_angle = -1.0

    return (
        math.acos(cos_angle)
        * 180.0
        / math.pi
    )


# ============================================================
# 공식 CanMV 방식의 FIST 판정
#
# 공식 hand_keypoint_class.py:
#
# thumb > 53도
# index/middle/ring/pinky > 65도
# ============================================================

def is_fist(points):

    angles = []

    for i in range(5):

        j = i * 8

        # 공식 CanMV 코드와 동일한 벡터 구성
        v1x = float(
            points[0] - points[j + 4]
        )

        v1y = float(
            points[1] - points[j + 5]
        )

        v2x = float(
            points[j + 6] - points[j + 8]
        )

        v2y = float(
            points[j + 7] - points[j + 9]
        )

        angle = vector_angle(
            v1x,
            v1y,
            v2x,
            v2y
        )

        angles.append(angle)


    for a in angles:

        if a == 65535.0:
            return False


    # 공식 CanMV fist 기준
    if (
        angles[0] > 53.0
        and angles[1] > 65.0
        and angles[2] > 65.0
        and angles[3] > 65.0
        and angles[4] > 65.0
    ):
        return True


    return False


# ============================================================
# MOVE / CLICK / DRAG / STOP
# ============================================================

class GestureController:

    def __init__(self, pointer_size=None):

        # ----------------------------------------------------
        # CLICK = 엄지 + 검지 pinch
        # ----------------------------------------------------

        self.pinch_on_ratio = 0.38
        self.pinch_off_ratio = 0.52

        # pinch가 이 시간 이상 유지되면 실제 CLICK
        self.click_confirm_ms = 90

        # 클릭 이후 손가락을 다시 벌려야 다음 클릭 가능
        self.click_rearm_ms = 120

        # 화면에 CLICK 표시하는 시간
        self.click_display_ms = 250


        # ----------------------------------------------------
        # DRAG = FIST
        # ----------------------------------------------------

        # 주먹이 이 시간 이상 유지되어야 DRAG 시작
        self.fist_confirm_ms = 180

        # 주먹이 순간 풀려도 이 시간까지는 DRAG 유지
        self.fist_release_ms = 220


        # ----------------------------------------------------
        # 손 인식 순간 유실
        # ----------------------------------------------------

        # 이 정도 짧은 유실은 무시
        self.hand_loss_grace_ms = 350


        # ----------------------------------------------------
        # 내부 상태
        # ----------------------------------------------------

        self.action = "STOP"

        self.dragging = False

        self.fist_since = None
        self.fist_release_since = None

        self.click_armed = False

        self.pinch_since = None
        self.open_since = None

        self.click_time = -10000

        self.last_seen_ms = None


        # ----------------------------------------------------
        # 포인터 smoothing
        # ----------------------------------------------------

        self.smooth_x = None
        self.smooth_y = None

        self.last_raw_x = None
        self.last_raw_y = None


        # ----------------------------------------------------
        # Cursor anchors
        #
        # Gesture recognition still uses the original keypoints and timings.
        # These values only decide which already-computed coordinate is sent
        # while a pinch/fist transition is in progress.
        # ----------------------------------------------------

        self.cursor_x = None
        self.cursor_y = None

        self.click_anchor_x = None
        self.click_anchor_y = None

        self.fist_anchor_x = None
        self.fist_anchor_y = None

        self.drag_start_palm_x = None
        self.drag_start_palm_y = None
        self.drag_start_cursor_x = None
        self.drag_start_cursor_y = None
        self.drag_filtered_palm_x = None
        self.drag_filtered_palm_y = None


        # ----------------------------------------------------
        # Relative movement pointer
        # ----------------------------------------------------

        self.pointer_float_x = None
        self.pointer_float_y = None
        self.pointer_ref_x = None
        self.pointer_ref_y = None
        self.pointer_filter_x = OneEuroFilter()
        self.pointer_filter_y = OneEuroFilter()

        if pointer_size is None:
            self.pointer_width = None
            self.pointer_height = None
        else:
            self.pointer_width = float(pointer_size[0])
            self.pointer_height = float(pointer_size[1])


    # ========================================================
    # 검지 포인터 smoothing
    #
    # 빨리 움직이면 거의 바로 따라감
    # 천천히 움직이면 떨림 제거
    # ========================================================

    def smooth_point(self, x, y):

        if self.smooth_x is None:

            self.smooth_x = float(x)
            self.smooth_y = float(y)

            self.last_raw_x = x
            self.last_raw_y = y

            return x, y


        dx = x - self.last_raw_x
        dy = y - self.last_raw_y

        speed = math.sqrt(
            dx * dx
            +
            dy * dy
        )


        self.last_raw_x = x
        self.last_raw_y = y


        if speed > 35:

            alpha = 0.90

        elif speed > 15:

            alpha = 0.72

        elif speed > 5:

            alpha = 0.52

        else:

            alpha = 0.32


        self.smooth_x = (
            self.smooth_x * (1.0 - alpha)
            +
            x * alpha
        )


        self.smooth_y = (
            self.smooth_y * (1.0 - alpha)
            +
            y * alpha
        )


        return (
            int(self.smooth_x),
            int(self.smooth_y)
        )


    def cursor_or_point(self, x, y):

        if self.cursor_x is None:
            return int(self.pointer_float_x), int(self.pointer_float_y)

        return self.cursor_x, self.cursor_y


    def hold_pointer_control(self, hand_x, hand_y, now):
        """Pause MOVE and reset its filter and spatial reference."""

        self.pointer_filter_x.reset(hand_x, now)
        self.pointer_filter_y.reset(hand_y, now)
        self.pointer_ref_x = float(hand_x)
        self.pointer_ref_y = float(hand_y)

    def delta_pointer_point(self, hand_x, hand_y, now):
        """Move by filtered index-tip displacement beyond a stable radius."""

        if self.pointer_float_x is None:

            if self.pointer_width is None:
                self.pointer_float_x = 0.0
                self.pointer_float_y = 0.0
            else:
                self.pointer_float_x = self.pointer_width / 2.0
                self.pointer_float_y = self.pointer_height / 2.0

            self.hold_pointer_control(hand_x, hand_y, now)

            return int(self.pointer_float_x), int(self.pointer_float_y)

        if self.pointer_ref_x is None:
            self.hold_pointer_control(hand_x, hand_y, now)
            return int(self.pointer_float_x), int(self.pointer_float_y)

        filtered_x = self.pointer_filter_x.filter(hand_x, now)
        filtered_y = self.pointer_filter_y.filter(hand_y, now)
        delta_x = filtered_x - self.pointer_ref_x
        delta_y = filtered_y - self.pointer_ref_y
        distance = math.sqrt(delta_x * delta_x + delta_y * delta_y)

        # Leave the reference still inside the radius. Outside, follow only
        # the excess distance, so a boundary crossing cannot jump the cursor.
        if distance > POINTER_DEAD_ZONE:
            fraction = (distance - POINTER_DEAD_ZONE) / distance
            move_x = delta_x * fraction
            move_y = delta_y * fraction
            self.pointer_float_x += move_x * POINTER_DELTA_GAIN
            self.pointer_float_y += move_y * POINTER_DELTA_GAIN
            self.pointer_ref_x += move_x
            self.pointer_ref_y += move_y

        # Keep the internal coordinate aligned with MouseController's screen
        # coordinate range.  Without this, movement past an OS screen edge
        # would build up invisible distance before a reverse movement reacts.
        if self.pointer_width is not None:
            if self.pointer_float_x < 0:
                self.pointer_float_x = 0.0
            elif self.pointer_float_x > self.pointer_width:
                self.pointer_float_x = self.pointer_width

            if self.pointer_float_y < 0:
                self.pointer_float_y = 0.0
            elif self.pointer_float_y > self.pointer_height:
                self.pointer_float_y = self.pointer_height

        return (
            int(self.pointer_float_x),
            int(self.pointer_float_y)
        )


    def drag_relative_point(self, palm_x, palm_y):
        """Return a noise-resistant palm-relative drag position."""

        self.drag_filtered_palm_x = (
            self.drag_filtered_palm_x * (1.0 - DRAG_PALM_ALPHA)
            + palm_x * DRAG_PALM_ALPHA
        )

        self.drag_filtered_palm_y = (
            self.drag_filtered_palm_y * (1.0 - DRAG_PALM_ALPHA)
            + palm_y * DRAG_PALM_ALPHA
        )

        delta_x = self.drag_filtered_palm_x - self.drag_start_palm_x
        delta_y = self.drag_filtered_palm_y - self.drag_start_palm_y

        if abs(delta_x) <= DRAG_DEAD_ZONE:
            delta_x = 0
        if abs(delta_y) <= DRAG_DEAD_ZONE:
            delta_y = 0

        return (
            int(self.drag_start_cursor_x + delta_x),
            int(self.drag_start_cursor_y + delta_y)
        )


    def result(self, action, x, y, pinch_ratio, fist, click_ready):

        if self.pointer_width is not None:
            x = max(0, min(int(x), int(self.pointer_width)))
            y = max(0, min(int(y), int(self.pointer_height)))

        self.cursor_x = int(x)
        self.cursor_y = int(y)

        if self.fist_since is not None or self.dragging or self.click_anchor_x is not None:
            self.pointer_float_x = float(self.cursor_x)
            self.pointer_float_y = float(self.cursor_y)

        return {
            "action": action,
            "x": self.cursor_x,
            "y": self.cursor_y,
            "pinch_ratio": pinch_ratio,
            "fist": fist,
            "click_ready": click_ready
        }


    def clear_cursor_locks(self):

        self.click_anchor_x = None
        self.click_anchor_y = None

        self.fist_anchor_x = None
        self.fist_anchor_y = None

        self.drag_start_palm_x = None
        self.drag_start_palm_y = None
        self.drag_start_cursor_x = None
        self.drag_start_cursor_y = None
        self.drag_filtered_palm_x = None
        self.drag_filtered_palm_y = None


    # ========================================================
    # 손이 잠깐 안 잡혔을 때
    # ========================================================

    def no_hand(self):

        now = time.ticks_ms()

        # A pinch must be continuous across detected frames. A brief detector
        # miss still keeps MOVE/DRAG grace, but cannot advance CLICK timing.
        if self.pinch_since is not None:
            self.pinch_since = None
            self.click_anchor_x = None
            self.click_anchor_y = None

        # A missing frame must not become a large MOVE delta on reacquisition.
        self.pointer_ref_x = None
        self.pointer_ref_y = None
        self.pointer_filter_x.reset()
        self.pointer_filter_y.reset()
        self.smooth_x = None
        self.smooth_y = None
        self.last_raw_x = None
        self.last_raw_y = None


        if self.last_seen_ms is None:

            self.action = "STOP"
            return self.action


        lost_ms = time.ticks_diff(
            now,
            self.last_seen_ms
        )


        # ----------------------------------------------------
        # 순간적인 detector miss
        #
        # 바로 STOP 하지 않는다.
        # ----------------------------------------------------

        if lost_ms < self.hand_loss_grace_ms:

            if self.dragging:

                self.action = "DRAG"

            else:

                click_elapsed = time.ticks_diff(
                    now,
                    self.click_time
                )

                if click_elapsed < self.click_display_ms:

                    self.action = "CLICK"

                else:

                    self.action = "MOVE"


            return self.action


        # ----------------------------------------------------
        # 진짜 손이 사라졌음
        # ----------------------------------------------------

        self.action = "STOP"

        self.dragging = False

        self.fist_since = None
        self.fist_release_since = None

        self.click_armed = False

        self.pinch_since = None
        self.open_since = None

        self.smooth_x = None
        self.smooth_y = None

        self.last_raw_x = None
        self.last_raw_y = None

        self.clear_cursor_locks()


        return self.action


    # ========================================================
    # 손 있음
    # ========================================================

    def update(
        self,
        points,
        fist_now
    ):

        now = time.ticks_ms()

        self.last_seen_ms = now


        # ----------------------------------------------------
        # 주요 keypoint
        # ----------------------------------------------------

        wrist_x = int(points[0])
        wrist_y = int(points[1])

        thumb_x = int(
            points[4 * 2]
        )

        thumb_y = int(
            points[4 * 2 + 1]
        )

        index_x = int(
            points[8 * 2]
        )

        index_y = int(
            points[8 * 2 + 1]
        )

        index_mcp_x = int(
            points[5 * 2]
        )

        index_mcp_y = int(
            points[5 * 2 + 1]
        )

        middle_mcp_x = int(
            points[9 * 2]
        )

        middle_mcp_y = int(
            points[9 * 2 + 1]
        )

        pinky_mcp_x = int(
            points[17 * 2]
        )

        pinky_mcp_y = int(
            points[17 * 2 + 1]
        )


        # Wrist and MCP joints remain comparatively stable while making a
        # fist. They are used only for relative movement after DRAG starts.
        palm_x = int(
            (wrist_x + index_mcp_x + middle_mcp_x + pinky_mcp_x)
            / 4
        )

        palm_y = int(
            (wrist_y + index_mcp_y + middle_mcp_y + pinky_mcp_y)
            / 4
        )


        # ----------------------------------------------------
        # 포인터
        # ----------------------------------------------------

        hand_x, hand_y = self.smooth_point(
            index_x,
            index_y
        )

        if self.pointer_float_x is None:
            self.delta_pointer_point(index_x, index_y, now)


        # ----------------------------------------------------
        # CLICK용 pinch 거리
        # ----------------------------------------------------

        pinch_distance = distance_xy(
            thumb_x,
            thumb_y,
            index_x,
            index_y
        )


        palm_width = distance_xy(
            index_mcp_x,
            index_mcp_y,
            pinky_mcp_x,
            pinky_mcp_y
        )


        palm_length = distance_xy(
            wrist_x,
            wrist_y,
            middle_mcp_x,
            middle_mcp_y
        )


        palm_scale = max(
            palm_width,
            palm_length
        )


        if palm_scale < 1:

            palm_scale = 1


        pinch_ratio = (
            pinch_distance
            /
            palm_scale
        )


        # ====================================================
        # 1순위: DRAG / FIST
        #
        # FIST가 잡힌 동안에는
        # CLICK 판정을 아예 하지 않는다.
        # ====================================================

        if fist_now:

            # A FIST candidate must not continue regular MOVE movement.
            self.hold_pointer_control(index_x, index_y, now)

            # release 후보 취소
            self.fist_release_since = None


            if self.dragging:

                self.action = "DRAG"

                drag_x, drag_y = self.drag_relative_point(
                    palm_x,
                    palm_y
                )

                return self.result(
                    self.action,
                    drag_x,
                    drag_y,
                    pinch_ratio,
                    True,
                    False
                )


            # 처음 주먹이 보임
            if self.fist_since is None:

                self.fist_since = now

                # An interrupted pinch cannot resume its old confirm timer
                # after a short FIST candidate ends.
                self.pinch_since = None
                self.click_anchor_x = None
                self.click_anchor_y = None

                self.fist_anchor_x, self.fist_anchor_y = (
                    self.cursor_or_point(
                        hand_x,
                        hand_y
                    )
                )


            fist_ms = time.ticks_diff(
                now,
                self.fist_since
            )


            # 일정 시간 안정적으로 주먹
            if fist_ms >= self.fist_confirm_ms:

                self.dragging = True

                self.click_armed = False

                self.pinch_since = None
                self.open_since = None

                self.action = "DRAG"

                self.drag_start_palm_x = palm_x
                self.drag_start_palm_y = palm_y
                self.drag_start_cursor_x = self.fist_anchor_x
                self.drag_start_cursor_y = self.fist_anchor_y
                self.drag_filtered_palm_x = float(palm_x)
                self.drag_filtered_palm_y = float(palm_y)


            else:

                # 아직 주먹 확인 중
                self.action = "MOVE"


            return self.result(
                self.action,
                self.fist_anchor_x,
                self.fist_anchor_y,
                pinch_ratio,
                True,
                False
            )


        # ====================================================
        # 현재 프레임은 FIST가 아님
        # ====================================================

        self.fist_since = None


        # ====================================================
        # 이미 DRAG 중
        #
        # 주먹이 한두 프레임 풀렸다고
        # 즉시 DRAG 종료하지 않는다.
        # ====================================================

        if self.dragging:

            if self.fist_release_since is None:

                self.fist_release_since = now


            release_ms = time.ticks_diff(
                now,
                self.fist_release_since
            )


            if release_ms < self.fist_release_ms:

                self.action = "DRAG"

                drag_x, drag_y = self.drag_relative_point(
                    palm_x,
                    palm_y
                )

                return self.result(
                    self.action,
                    drag_x,
                    drag_y,
                    pinch_ratio,
                    False,
                    False
                )


            # -----------------------------------------------
            # 확실히 주먹을 풀었음
            # -----------------------------------------------

            self.dragging = False

            self.fist_release_since = None

            # 바로 CLICK 되는 것 방지
            self.click_armed = False

            self.pinch_since = None
            self.open_since = now

            # The drag result is the last actual output coordinate.
            self.pointer_float_x = float(self.cursor_x)
            self.pointer_float_y = float(self.cursor_y)
            self.hold_pointer_control(index_x, index_y, now)

            self.clear_cursor_locks()

            self.action = "MOVE"


        # ====================================================
        # CLICK 재활성화
        #
        # CLICK이나 DRAG 후에는
        # 엄지/검지가 확실히 벌어져야 다시 CLICK 가능
        # ====================================================

        if not self.click_armed:

            if pinch_ratio > self.pinch_off_ratio:

                if self.open_since is None:

                    self.open_since = now


                open_ms = time.ticks_diff(
                    now,
                    self.open_since
                )


                if open_ms >= self.click_rearm_ms:

                    self.click_armed = True

                    self.open_since = None
                    self.pinch_since = None
                    if self.click_anchor_x is not None:
                        self.hold_pointer_control(index_x, index_y, now)
                    self.click_anchor_x = None
                    self.click_anchor_y = None


            else:

                self.open_since = None


        # ====================================================
        # CLICK 판정
        #
        # 이제 CLICK과 DRAG는 완전히 다른 제스처임.
        #
        # CLICK = PINCH
        # DRAG  = FIST
        # ====================================================

        if self.click_armed:

            if pinch_ratio < self.pinch_on_ratio:

                if self.pinch_since is None:

                    self.pinch_since = now

                    self.click_anchor_x, self.click_anchor_y = (
                        self.cursor_or_point(
                            hand_x,
                            hand_y
                        )
                    )


                pinch_ms = time.ticks_diff(
                    now,
                    self.pinch_since
                )


                if pinch_ms >= self.click_confirm_ms:

                    print(
                        "CLICK_DECISION",
                        "ms=", now,
                        "action=CLICK",
                        "pinch_ratio=", pinch_ratio,
                        "pinch_since=", self.pinch_since,
                        "pinch_confirm_ms=", pinch_ms,
                        "click_armed=", self.click_armed,
                        "click_locked=", self.click_anchor_x is not None,
                        "rearm_since=", self.open_since,
                        "fist=", fist_now,
                        "fist_since=", self.fist_since,
                        "drag=", self.dragging,
                        "hand_present=True"
                    )

                    # CLICK은 1회만 발생
                    self.click_time = now

                    self.action = "CLICK"

                    self.click_armed = False

                    self.pinch_since = None
                    self.open_since = None


                    return self.result(
                        self.action,
                        self.click_anchor_x,
                        self.click_anchor_y,
                        pinch_ratio,
                        False,
                        False
                    )


            else:

                if self.pinch_since is not None or self.click_anchor_x is not None:
                    self.hold_pointer_control(index_x, index_y, now)
                self.pinch_since = None
                self.click_anchor_x = None
                self.click_anchor_y = None


        # ====================================================
        # CLICK 표시 유지
        # ====================================================

        click_elapsed = time.ticks_diff(
            now,
            self.click_time
        )


        if click_elapsed < self.click_display_ms:

            self.action = "CLICK"

        else:

            self.action = "MOVE"


        if (
            self.pinch_since is not None
            or
            (
                self.click_anchor_x is not None
                and not self.click_armed
            )
        ):

            # Keep MOVE rebased while the click anchor is held.
            self.hold_pointer_control(index_x, index_y, now)

            output_x = self.click_anchor_x
            output_y = self.click_anchor_y

        else:

            output_x, output_y = self.delta_pointer_point(
                index_x,
                index_y,
                now
            )

        return self.result(
            self.action,
            output_x,
            output_y,
            pinch_ratio,
            False,
            self.click_armed
        )
