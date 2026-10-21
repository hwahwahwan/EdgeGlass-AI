# ============================================================
# 웹 영상 스트리밍용 RGB565 JPEG 인코딩 모듈
# ============================================================
#
# wifi_test/jpeg_format_test.py / mjpeg_stream_test.py에서 실기기로
# 검증한 내용만 반영한다:
#   - Sensor.YUV420SP + Image.compress()는 색상 왜곡 + 좌우 중복을
#     일으킨다(실측 재현, wifi_test/WIFI_TEST_REPORT.md §8 참고).
#   - Sensor.RGB565 + Image.compress()는 정상 JPEG을 만든다.
#   - compress()는 원본과 분리된 새 Image 객체를 반환하므로, 바이트는
#     반드시 그 반환값에서 꺼내야 한다(원본 img가 아니라).
#   - img.size()는 압축 후에도 원본 버퍼 전체 크기를 반환하므로 쓰면
#     안 되고, len(compressed_img) / compressed_img.bytearray()를
#     그대로 써야 한다.
#
# 이 모듈은 어떤 채널/센서에서 Image를 얻었는지 신경 쓰지 않는다 —
# 오케스트레이터가 "RGB565로 설정된 채널의 snapshot() 결과"를 넘겨주는
# 것을 전제로 한다.

import time


def encode_jpeg(img, quality=50):
    """RGB565 Image를 JPEG bytes로 인코딩한다.

    Returns:
        (jpeg_bytes, encode_ms)
    """
    t0 = time.ticks_ms()
    jpeg_img = img.compress(quality=quality)
    data = bytes(jpeg_img.bytearray())
    encode_ms = time.ticks_diff(time.ticks_ms(), t0)
    return data, encode_ms
