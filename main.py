from libs.PipeLine import PipeLine
from media.media import *

import sys
import gc
import time

# This project is stored as a directory on the persistent SD card.  CanMV's
# default sys.path includes /sdcard, but not its child project directories.
PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from hand_tracker import HandTracker
from gesture_controller import GestureController, is_fist
from mouse_controller import MouseController
from ui import draw_hand


# Enable only while collecting OPEN/FIST tracking measurements on the board.
TRACKING_DIAGNOSTICS = False


def tracking_sample(det, points, crop, fallback, fist_now):
    """Read existing detector/ROI/keypoint results without changing them."""
    crop_x, crop_y, side, _ = crop
    palm_x = (int(points[0]) + int(points[10]) + int(points[18]) + int(points[34])) / 4
    palm_y = (int(points[1]) + int(points[11]) + int(points[19]) + int(points[35])) / 4
    return (
        (float(det[2]) + float(det[4])) / 2,
        (float(det[3]) + float(det[5])) / 2,
        float(det[4]) - float(det[2]),
        float(det[5]) - float(det[3]),
        crop_x + side / 2,
        crop_y + side / 2,
        side,
        int(points[0]), int(points[1]),
        palm_x, palm_y,
        int(points[16]), int(points[17]),
        (int(points[0]) - crop_x) / side,
        (int(points[1]) - crop_y) / side,
        (int(points[16]) - crop_x) / side,
        (int(points[17]) - crop_y) / side,
        int(fallback), int(fist_now)
    )


def send_tracking(uart, kind, frame, sample=None, delta=None):
    """Best-effort diagnostics on UART2, separate from @MOUSE records."""
    try:
        now = time.ticks_ms()
        if kind == "L":
            record = "@TRACK|L|%d|%d\r\n" % (now, frame)
        else:
            values = ",".join(str(value) for value in sample)
            changes = "" if delta is None else ",".join(str(value) for value in delta)
            record = "@TRACK|S|%d|%d|%s|%s\r\n" % (
                now, frame, values, changes
            )
        uart.write(record)
    except Exception:
        pass


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
        GestureController(rgb888p_size)
    )

    # Transport only: GestureController remains the sole owner of AI,
    # gesture recognition, state transitions, and pointer smoothing.
    mouse_controller = MouseController(
        rgb888p_size
    )


    frame_count = 0
    last_action = None
    tracking_previous = None


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

                if TRACKING_DIAGNOSTICS:
                    tracking_previous = None

                action = (
                    gesture_controller.no_hand()
                )

                mouse_controller.update(
                    action
                )

                if TRACKING_DIAGNOSTICS:
                    send_tracking(mouse_controller.uart, "L", frame_count)


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

                if TRACKING_DIAGNOSTICS:
                    sample = tracking_sample(
                        det, points, tracker.keypoint.crop_params,
                        fallback, fist_now
                    )
                    delta = None
                    if tracking_previous is not None:
                        delta = tuple(
                            sample[i] - tracking_previous[i]
                            for i in range(len(sample) - 2)
                        )
                    tracking_previous = sample


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

                mouse_controller.update(
                    action,
                    info["x"],
                    info["y"]
                )

                if TRACKING_DIAGNOSTICS:
                    send_tracking(mouse_controller.uart, "S", frame_count,
                                  sample, delta)


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

        # Sends DRAG_END before teardown if the K230 was dragging.
        mouse_controller.close()


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
