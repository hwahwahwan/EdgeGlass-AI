import math
import time


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

    def __init__(self):

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


    # ========================================================
    # 손이 잠깐 안 잡혔을 때
    # ========================================================

    def no_hand(self):

        now = time.ticks_ms()


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


        # ----------------------------------------------------
        # 포인터
        # ----------------------------------------------------

        move_x, move_y = self.smooth_point(
            index_x,
            index_y
        )


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

            # release 후보 취소
            self.fist_release_since = None


            if self.dragging:

                self.action = "DRAG"


                return {
                    "action": self.action,
                    "x": move_x,
                    "y": move_y,

                    "pinch_ratio": pinch_ratio,

                    "fist": True,
                    "click_ready": False
                }


            # 처음 주먹이 보임
            if self.fist_since is None:

                self.fist_since = now


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


            else:

                # 아직 주먹 확인 중
                self.action = "MOVE"


            return {
                "action": self.action,
                "x": move_x,
                "y": move_y,

                "pinch_ratio": pinch_ratio,

                "fist": True,
                "click_ready": False
            }


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


                return {
                    "action": self.action,
                    "x": move_x,
                    "y": move_y,

                    "pinch_ratio": pinch_ratio,

                    "fist": False,
                    "click_ready": False
                }


            # -----------------------------------------------
            # 확실히 주먹을 풀었음
            # -----------------------------------------------

            self.dragging = False

            self.fist_release_since = None

            # 바로 CLICK 되는 것 방지
            self.click_armed = False

            self.pinch_since = None
            self.open_since = now

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


                pinch_ms = time.ticks_diff(
                    now,
                    self.pinch_since
                )


                if pinch_ms >= self.click_confirm_ms:

                    # CLICK은 1회만 발생
                    self.click_time = now

                    self.action = "CLICK"

                    self.click_armed = False

                    self.pinch_since = None
                    self.open_since = None


                    return {
                        "action": self.action,
                        "x": move_x,
                        "y": move_y,

                        "pinch_ratio": pinch_ratio,

                        "fist": False,
                        "click_ready": False
                    }


            else:

                self.pinch_since = None


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


        return {
            "action": self.action,

            "x": move_x,
            "y": move_y,

            "pinch_ratio": pinch_ratio,

            "fist": False,

            "click_ready": self.click_armed
        }


