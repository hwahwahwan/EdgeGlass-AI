from libs.PipeLine import PipeLine
from media.media import *

import sys
import gc

# This project is stored as a directory on the persistent SD card.  CanMV's
# default sys.path includes /sdcard, but not its child project directories.
PROJECT_DIR = "/sdcard/smart_glass"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from hand_tracker import HandTracker
from gesture_controller import GestureController, is_fist
from mouse_controller import MouseController
from ui import draw_hand


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

                mouse_controller.update(
                    action
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

                mouse_controller.update(
                    action,
                    info["x"],
                    info["y"]
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
