from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
from media.media import ALIGN_UP

import nncase_runtime as nn
import ulab.numpy as np
import aicube


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

