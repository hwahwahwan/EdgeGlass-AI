from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *

from media.media import *

import sys
import gc
import math
import time

import nncase_runtime as nn
import ulab.numpy as np
import image
import aicube


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


# ============================================================
# 손바닥 검출
# ============================================================

class HandDetection(AIBase):

    def __init__(
        self,
        kmodel_path,
        model_input_size,
        labels,
        anchors,

        confidence_threshold=0.2,
        nms_threshold=0.5,

        strides=[8, 16, 32],

        rgb888p_size=[640, 360],

        debug_mode=0
    ):

        super().__init__(
            kmodel_path,
            model_input_size,
            rgb888p_size,
            debug_mode
        )


        self.model_input_size = model_input_size

        self.labels = labels
        self.anchors = anchors

        self.strides = strides

        self.confidence_threshold = (
            confidence_threshold
        )

        self.nms_threshold = (
            nms_threshold
        )


        self.rgb888p_size = [
            ALIGN_UP(
                rgb888p_size[0],
                16
            ),

            rgb888p_size[1]
        ]


        self.ai2d = Ai2d(
            debug_mode
        )


        self.ai2d.set_ai2d_dtype(
            nn.ai2d_format.NCHW_FMT,
            nn.ai2d_format.NCHW_FMT,

            np.uint8,
            np.uint8
        )


    def config_preprocess(
        self,
        input_image_size=None
    ):

        input_size = (
            input_image_size
            if input_image_size
            else self.rgb888p_size
        )


        top, bottom, left, right, _ = (
            center_pad_param(
                self.rgb888p_size,
                self.model_input_size
            )
        )


        self.ai2d.pad(
            [
                0, 0, 0, 0,

                top,
                bottom,
                left,
                right
            ],

            0,

            [
                114,
                114,
                114
            ]
        )


        self.ai2d.resize(
            nn.interp_method.tf_bilinear,
            nn.interp_mode.half_pixel
        )


        self.ai2d.build(
            [
                1,
                3,
                input_size[1],
                input_size[0]
            ],

            [
                1,
                3,
                self.model_input_size[1],
                self.model_input_size[0]
            ]
        )


    def postprocess(
        self,
        results
    ):

        return aicube.anchorbasedet_post_process(
            results[0],
            results[1],
            results[2],

            self.model_input_size,
            self.rgb888p_size,

            self.strides,

            len(
                self.labels
            ),

            self.confidence_threshold,
            self.nms_threshold,

            self.anchors,

            False
        )


# ============================================================
# 손 키포인트
# ============================================================

class HandKeypoint(AIBase):

    def __init__(
        self,
        kmodel_path,
        model_input_size,

        rgb888p_size=[640, 360],

        debug_mode=0
    ):

        super().__init__(
            kmodel_path,
            model_input_size,
            rgb888p_size,
            debug_mode
        )


        self.model_input_size = (
            model_input_size
        )


        self.rgb888p_size = [
            ALIGN_UP(
                rgb888p_size[0],
                16
            ),

            rgb888p_size[1]
        ]


        self.crop_params = [
            0,
            0,
            1,
            1
        ]


        self.ai2d = Ai2d(
            debug_mode
        )


        self.ai2d.set_ai2d_dtype(
            nn.ai2d_format.NCHW_FMT,
            nn.ai2d_format.NCHW_FMT,

            np.uint8,
            np.uint8
        )


    # ========================================================
    # 정사각형 ROI 유지
    #
    # 화면 끝에 가더라도
    # ROI 자체를 안쪽으로 이동시킴
    # ========================================================

    def get_square_crop(
        self,
        det
    ):

        frame_w = (
            self.rgb888p_size[0]
        )

        frame_h = (
            self.rgb888p_size[1]
        )


        x1 = float(det[2])
        y1 = float(det[3])

        x2 = float(det[4])
        y2 = float(det[5])


        w = x2 - x1
        h = y2 - y1


        cx = (
            x1 + x2
        ) / 2.0

        cy = (
            y1 + y2
        ) / 2.0


        # 공식 1.26보다 아주 조금 여유 있게
        side = int(
            max(w, h)
            *
            1.30
        )


        if side < 32:

            side = 32


        max_side = min(
            frame_w,
            frame_h
        )


        if side > max_side:

            side = max_side


        crop_x = int(
            cx - side / 2
        )

        crop_y = int(
            cy - side / 2
        )


        # 자르지 않고 위치를 이동
        if crop_x < 0:

            crop_x = 0


        if crop_y < 0:

            crop_y = 0


        if crop_x + side > frame_w:

            crop_x = (
                frame_w
                -
                side
            )


        if crop_y + side > frame_h:

            crop_y = (
                frame_h
                -
                side
            )


        return [
            int(crop_x),
            int(crop_y),

            int(side),
            int(side)
        ]


    def config_preprocess(
        self,
        det,
        input_image_size=None
    ):

        input_size = (
            input_image_size
            if input_image_size
            else self.rgb888p_size
        )


        self.crop_params = (
            self.get_square_crop(
                det
            )
        )


        self.ai2d.crop(
            self.crop_params[0],
            self.crop_params[1],

            self.crop_params[2],
            self.crop_params[3]
        )


        self.ai2d.resize(
            nn.interp_method.tf_bilinear,
            nn.interp_mode.half_pixel
        )


        self.ai2d.build(
            [
                1,
                3,
                input_size[1],
                input_size[0]
            ],

            [
                1,
                3,
                self.model_input_size[1],
                self.model_input_size[0]
            ]
        )


    def postprocess(
        self,
        results
    ):

        values = results[0].reshape(
            results[0].shape[0]
            *
            results[0].shape[1]
        )


        points = np.zeros(
            values.shape,
            dtype=np.int16
        )


        crop_x = (
            self.crop_params[0]
        )

        crop_y = (
            self.crop_params[1]
        )

        side = (
            self.crop_params[2]
        )


        points[0::2] = (
            values[0::2]
            *
            side
            +
            crop_x
        )


        points[1::2] = (
            values[1::2]
            *
            side
            +
            crop_y
        )


        return points


# ============================================================
# 손 추적
# ============================================================

class HandTracker:

    def __init__(
        self,

        hand_det_model,
        hand_kp_model,

        rgb888p_size
    ):

        self.rgb888p_size = (
            rgb888p_size
        )


        anchors = [
            26, 27,
            53, 52,
            75, 71,
            80, 99,
            106, 82,
            99, 134,
            140, 113,
            161, 172,
            245, 276
        ]


        self.detector = HandDetection(
            hand_det_model,

            model_input_size=[
                512,
                512
            ],

            labels=[
                "hand"
            ],

            anchors=anchors,

            confidence_threshold=0.2,

            nms_threshold=0.5,

            rgb888p_size=rgb888p_size
        )


        self.keypoint = HandKeypoint(
            hand_kp_model,

            model_input_size=[
                256,
                256
            ],

            rgb888p_size=rgb888p_size
        )


        self.detector.config_preprocess()


        # ----------------------------------------------------
        # detector가 딱 1~2프레임 놓쳤을 때
        # 마지막 bbox 재사용
        # ----------------------------------------------------

        self.last_det = None

        self.det_miss_count = 0

        self.det_miss_grace_frames = 2


    # ========================================================
    # 공식 CanMV와 비슷한 edge filtering
    #
    # 이전 버전처럼 화면 끝에 조금 닿았다고
    # 손 전체를 버리지 않는다.
    # ========================================================

    def detection_valid(
        self,
        det
    ):

        frame_w = (
            self.rgb888p_size[0]
        )

        frame_h = (
            self.rgb888p_size[1]
        )


        x1 = det[2]
        y1 = det[3]

        x2 = det[4]
        y2 = det[5]


        w = x2 - x1
        h = y2 - y1


        # 너무 작은 손
        if h < (
            0.10
            *
            frame_h
        ):

            return False


        # 공식 예제 방식:
        # 작은 검출이 가장자리에 걸린 경우만 제거
        if (
            w < (
                0.25
                *
                frame_w
            )
            and
            (
                x1 < (
                    0.03
                    *
                    frame_w
                )
                or
                x2 > (
                    0.97
                    *
                    frame_w
                )
            )
        ):

            return False


        if (
            w < (
                0.15
                *
                frame_w
            )
            and
            (
                x1 < (
                    0.01
                    *
                    frame_w
                )
                or
                x2 > (
                    0.99
                    *
                    frame_w
                )
            )
        ):

            return False


        return True


    # ========================================================
    # run
    # ========================================================

    def run(
        self,
        img
    ):

        detections = (
            self.detector.run(
                img
            )
        )


        best_det = None
        best_area = 0


        # ----------------------------------------------------
        # 정상 detector 결과 검색
        # ----------------------------------------------------

        for det in detections:

            if not self.detection_valid(
                det
            ):

                continue


            w = (
                det[4]
                -
                det[2]
            )

            h = (
                det[5]
                -
                det[3]
            )


            area = w * h


            # 가장 큰 손 사용
            if area > best_area:

                best_area = area
                best_det = det


        used_fallback = False


        # ----------------------------------------------------
        # detector 성공
        # ----------------------------------------------------

        if best_det is not None:

            self.last_det = best_det

            self.det_miss_count = 0


        # ----------------------------------------------------
        # detector가 순간 놓침
        #
        # 1~2프레임은 마지막 bbox로
        # keypoint를 다시 시도한다.
        # ----------------------------------------------------

        elif (
            self.last_det is not None
            and
            self.det_miss_count
            <
            self.det_miss_grace_frames
        ):

            best_det = (
                self.last_det
            )

            self.det_miss_count += 1

            used_fallback = True


        # ----------------------------------------------------
        # 정말 손 없음
        # ----------------------------------------------------

        else:

            self.det_miss_count += 1

            return (
                None,
                None,
                False
            )


        # ----------------------------------------------------
        # Keypoint
        # ----------------------------------------------------

        self.keypoint.config_preprocess(
            best_det
        )


        points = self.keypoint.run(
            img
        )


        return (
            best_det,
            points,
            used_fallback
        )


# ============================================================
# 카메라 좌표 -> Preview 좌표
# ============================================================

def point_to_display(
    x,
    y,

    rgb_size,
    display_size
):

    dx = int(
        x
        *
        display_size[0]
        /
        rgb_size[0]
    )


    dy = int(
        y
        *
        display_size[1]
        /
        rgb_size[1]
    )


    return dx, dy


# ============================================================
# 손 그리기
# ============================================================

def draw_hand(
    pl,

    det,
    points,

    rgb888p_size,
    display_size,

    info
):

    # --------------------------------------------------------
    # 손 박스
    # --------------------------------------------------------

    x1, y1 = point_to_display(
        det[2],
        det[3],

        rgb888p_size,
        display_size
    )


    x2, y2 = point_to_display(
        det[4],
        det[5],

        rgb888p_size,
        display_size
    )


    pl.osd_img.draw_rectangle(
        x1,
        y1,

        x2 - x1,
        y2 - y1,

        color=(
            255,
            0,
            255,
            0
        ),

        thickness=2
    )


    # --------------------------------------------------------
    # 관절 점
    # --------------------------------------------------------

    for i in range(21):

        x = int(
            points[i * 2]
        )

        y = int(
            points[i * 2 + 1]
        )


        px, py = point_to_display(
            x,
            y,

            rgb888p_size,
            display_size
        )


        # 화면 밖이면 그리지만 않음
        if (
            px >= 0
            and
            py >= 0
            and
            px < display_size[0]
            and
            py < display_size[1]
        ):

            pl.osd_img.draw_circle(
                px,
                py,

                4,

                color=(
                    255,
                    255,
                    255,
                    255
                ),

                fill=True
            )


    # --------------------------------------------------------
    # Skeleton
    # --------------------------------------------------------

    connections = [

        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),

        (0, 5),
        (5, 6),
        (6, 7),
        (7, 8),

        (0, 9),
        (9, 10),
        (10, 11),
        (11, 12),

        (0, 13),
        (13, 14),
        (14, 15),
        (15, 16),

        (0, 17),
        (17, 18),
        (18, 19),
        (19, 20)
    ]


    for a, b in connections:

        ax = int(
            points[a * 2]
        )

        ay = int(
            points[a * 2 + 1]
        )

        bx = int(
            points[b * 2]
        )

        by = int(
            points[b * 2 + 1]
        )


        ax, ay = point_to_display(
            ax,
            ay,

            rgb888p_size,
            display_size
        )


        bx, by = point_to_display(
            bx,
            by,

            rgb888p_size,
            display_size
        )


        pl.osd_img.draw_line(
            ax,
            ay,
            bx,
            by,

            color=(
                255,
                0,
                255,
                0
            ),

            thickness=2
        )


    # --------------------------------------------------------
    # smoothing된 검지 포인터
    # --------------------------------------------------------

    pointer_x, pointer_y = (
        point_to_display(
            info["x"],
            info["y"],

            rgb888p_size,
            display_size
        )
    )


    pl.osd_img.draw_circle(
        pointer_x,
        pointer_y,

        10,

        color=(
            255,
            255,
            0,
            0
        ),

        fill=True
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # K230D Zero
    # --------------------------------------------------------

    display_mode = "auto"

    display_size = None


    rgb888p_size = [
        640,
        360
    ]


    # --------------------------------------------------------
    # 모델
    # --------------------------------------------------------

    hand_det_model = (
        "/sdcard/examples/kmodel/"
        "hand_det.kmodel"
    )


    hand_kp_model = (
        "/sdcard/examples/kmodel/"
        "handkp_det.kmodel"
    )


    pl = None
    tracker = None


    gesture_controller = (
        GestureController()
    )


    frame_count = 0
    last_action = None


    try:

        # ====================================================
        # Pipeline
        # ====================================================

        pl = PipeLine(
            rgb888p_size=rgb888p_size,

            display_mode=display_mode,

            display_size=display_size
        )


        pl.create()


        display_size = (
            pl.get_display_size()
        )


        print(
            "DISPLAY:",
            display_size
        )


        # ====================================================
        # AI
        # ====================================================

        tracker = HandTracker(
            hand_det_model,
            hand_kp_model,

            rgb888p_size
        )


        print(
            "Smart Glass START"
        )


        # ====================================================
        # LOOP
        # ====================================================

        while True:

            frame_count += 1


            img = (
                pl.get_frame()
            )


            det, points, fallback = (
                tracker.run(
                    img
                )
            )


            pl.osd_img.clear()


            # =================================================
            # 손 없음
            # =================================================

            if (
                det is None
                or
                points is None
            ):

                action = (
                    gesture_controller.no_hand()
                )


                pl.osd_img.draw_string_advanced(
                    30,
                    30,

                    40,

                    "ACTION: " + action,

                    color=(
                        255,
                        255,
                        0,
                        0
                    )
                )


                if action != last_action:

                    print(
                        "ACTION:",
                        action
                    )

                    last_action = action


            # =================================================
            # 손 있음
            # =================================================

            else:

                # ---------------------------------------------
                # 공식 CanMV 방식 FIST 판단
                # ---------------------------------------------

                fist_now = is_fist(
                    points
                )


                # ---------------------------------------------
                # MOVE / CLICK / DRAG
                # ---------------------------------------------

                info = (
                    gesture_controller.update(
                        points,
                        fist_now
                    )
                )


                action = (
                    info["action"]
                )


                # ---------------------------------------------
                # 관절 / 박스
                # ---------------------------------------------

                draw_hand(
                    pl,

                    det,
                    points,

                    rgb888p_size,
                    display_size,

                    info
                )


                # =============================================
                # ACTION
                # =============================================

                pl.osd_img.draw_string_advanced(
                    30,
                    30,

                    40,

                    "ACTION: " + action,

                    color=(
                        255,
                        255,
                        0,
                        0
                    )
                )


                # =============================================
                # 좌표
                # =============================================

                pl.osd_img.draw_string_advanced(
                    30,
                    80,

                    27,

                    "X:%d Y:%d" % (
                        info["x"],
                        info["y"]
                    ),

                    color=(
                        255,
                        255,
                        255,
                        255
                    )
                )


                # =============================================
                # PINCH
                # =============================================

                pl.osd_img.draw_string_advanced(
                    30,
                    115,

                    23,

                    "PINCH: %.2f" % (
                        info["pinch_ratio"]
                    ),

                    color=(
                        255,
                        255,
                        255,
                        255
                    )
                )


                # =============================================
                # FIST
                # =============================================

                if fist_now:

                    gesture_text = "FIST"

                else:

                    gesture_text = "OPEN"


                pl.osd_img.draw_string_advanced(
                    30,
                    145,

                    23,

                    "GESTURE: "
                    +
                    gesture_text,

                    color=(
                        255,
                        255,
                        255,
                        255
                    )
                )


                # =============================================
                # CLICK 준비 상태
                # =============================================

                if info["click_ready"]:

                    click_text = "CLICK READY"

                else:

                    click_text = "CLICK LOCK"


                pl.osd_img.draw_string_advanced(
                    30,
                    175,

                    20,

                    click_text,

                    color=(
                        255,
                        255,
                        255,
                        255
                    )
                )


                # =============================================
                # detector fallback 확인
                # =============================================

                if fallback:

                    pl.osd_img.draw_string_advanced(
                        30,
                        205,

                        18,

                        "TRACK HOLD",

                        color=(
                            255,
                            255,
                            255,
                            0
                        )
                    )


                # =============================================
                # 로그
                # =============================================

                if action != last_action:

                    print(
                        "ACTION:",
                        action,
                        "| FIST:",
                        fist_now,
                        "| PINCH:",
                        round(
                            info["pinch_ratio"],
                            2
                        )
                    )

                    last_action = action


                elif frame_count % 10 == 0:

                    print(
                        action,
                        "| FIST:",
                        fist_now,
                        "| P:",
                        round(
                            info["pinch_ratio"],
                            2
                        ),
                        "| fallback:",
                        fallback
                    )


            # =================================================
            # Preview
            # =================================================

            pl.show_image()


            # =================================================
            # GC
            # =================================================

            if frame_count % 12 == 0:

                gc.collect()


    except KeyboardInterrupt:

        print(
            "Stopped by user"
        )


    except BaseException as e:

        print(
            "ERROR:"
        )

        sys.print_exception(
            e
        )


    finally:

        print(
            "Cleaning up..."
        )


        if tracker is not None:

            try:

                tracker.detector.deinit()

            except:

                pass


            try:

                tracker.keypoint.deinit()

            except:

                pass


        if pl is not None:

            try:

                pl.destroy()

            except:

                pass


        gc.collect()


        print(
            "Done"
        )