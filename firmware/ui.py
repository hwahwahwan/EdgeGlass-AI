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
# 손 그리기 (공용 코어: 임의의 Image 객체에 그림)
# ============================================================
#
# draw_hand()가 pl.osd_img에만 그릴 수 있던 것을, 웹 스트리밍처럼
# 임의의 Image 객체(+별도 목표 해상도)에도 그릴 수 있도록 분리했다.
# 그리는 내용과 좌표 변환 로직은 기존 draw_hand()와 완전히 동일하다.

_SKELETON_CONNECTIONS = [

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


def draw_landmarks(
    image_obj,

    det,
    points,

    rgb888p_size,
    target_size
):

    # --------------------------------------------------------
    # 손 박스
    # --------------------------------------------------------

    x1, y1 = point_to_display(
        det[2],
        det[3],

        rgb888p_size,
        target_size
    )


    x2, y2 = point_to_display(
        det[4],
        det[5],

        rgb888p_size,
        target_size
    )


    image_obj.draw_rectangle(
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
            target_size
        )


        # 화면 밖이면 그리지만 않음
        if (
            px >= 0
            and
            py >= 0
            and
            px < target_size[0]
            and
            py < target_size[1]
        ):

            image_obj.draw_circle(
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

    for a, b in _SKELETON_CONNECTIONS:

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
            target_size
        )


        bx, by = point_to_display(
            bx,
            by,

            rgb888p_size,
            target_size
        )


        image_obj.draw_line(
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
    # 실제 검지 끝 landmark 8 (mouse cursor 좌표와 별개)
    # --------------------------------------------------------

    pointer_x, pointer_y = (
        point_to_display(
            points[16],
            points[17],

            rgb888p_size,
            target_size
        )
    )


    image_obj.draw_circle(
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


def draw_hand(
    pl,

    det,
    points,

    rgb888p_size,
    display_size,

    info
):

    # 디스플레이 OSD용 얇은 래퍼. main.py 호출부는 변경하지 않는다.
    draw_landmarks(
        pl.osd_img,

        det,
        points,

        rgb888p_size,
        display_size
    )

