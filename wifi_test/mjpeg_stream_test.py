import socket
import select
import time
import network
import gc
import os

from media.sensor import Sensor
from media.media import *

PORT = 8060
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
JPEG_QUALITY = 50
STREAM_SECONDS = 8
STREAM_MAX_FRAMES = 150
TOTAL_TIMEOUT_MS = 90000
REQUEST_TIMEOUT_MS = 3000
MAX_REQUEST_BYTES = 4096
# Raised from 5000: today's hotspot measured mid-send stalls >5s (OSError 110)
# even though the connection itself was alive; see WIFI_TEST_REPORT.md.
SEND_STALL_TIMEOUT_MS = 15000
SEND_CHUNK_BYTES = 8192

INDEX_HTML = b"""<!doctype html><html><head><meta charset='utf-8'>
<title>K230D mjpeg_test</title></head><body>
<h1>EdgeGlass-AI wifi_test MJPEG stream</h1>
<img src="/stream" width="640" height="480">
</body></html>"""


def log(msg):
    print("[MJPEG]", msg)


def error_code(error):
    return getattr(error, "errno", error.args[0] if error.args else None)


def send_all(client, data):
    view = memoryview(data)
    offset = 0
    deadline = time.ticks_add(time.ticks_ms(), SEND_STALL_TIMEOUT_MS)
    while offset < len(view):
        try:
            end = min(offset + SEND_CHUNK_BYTES, len(view))
            sent = client.send(view[offset:end])
        except OSError as e:
            if error_code(e) not in (11, 110):
                raise
            sent = 0
        if sent:
            offset += sent
            deadline = time.ticks_add(time.ticks_ms(), SEND_STALL_TIMEOUT_MS)
            continue
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)
        time.sleep_ms(5)


def read_path(client):
    request = bytearray()
    deadline = time.ticks_add(time.ticks_ms(), REQUEST_TIMEOUT_MS)
    client.setblocking(False)
    while len(request) < MAX_REQUEST_BYTES:
        try:
            chunk = client.recv(min(256, MAX_REQUEST_BYTES - len(request)))
        except OSError as e:
            if error_code(e) != 11:
                raise
            chunk = None
        if chunk:
            request.extend(chunk)
            if request.find(b"\r\n\r\n") >= 0 or request.find(b"\n\n") >= 0:
                break
        elif time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)
        else:
            time.sleep_ms(10)
    line = bytes(request).split(b"\r\n", 1)[0].split()
    if len(line) < 2:
        return "/"
    return line[1].decode().split("?", 1)[0]


def send_html(client, body):
    header = (
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n"
    ) % len(body)
    send_all(client, header.encode() + body)


def send_jpeg(client, jpeg_bytes):
    header = (
        "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\n"
        "Content-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n"
    ) % len(jpeg_bytes)
    send_t0 = time.ticks_ms()
    send_all(client, header.encode() + jpeg_bytes)
    send_ms = time.ticks_diff(time.ticks_ms(), send_t0)
    log("/snapshot sent bytes=%d send_ms=%d" % (len(jpeg_bytes), send_ms))


def capture_jpeg(sensor):
    t0 = time.ticks_ms()
    img = sensor.snapshot()
    jpeg_img = img.compress(quality=JPEG_QUALITY)
    data = bytes(jpeg_img.bytearray())
    encode_ms = time.ticks_diff(time.ticks_ms(), t0)
    return data, encode_ms


def stream_mjpeg(client, sensor):
    send_all(
        client,
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
        b"Connection: close\r\n\r\n",
    )
    deadline = time.ticks_add(time.ticks_ms(), STREAM_SECONDS * 1000)
    frame_count = 0
    first_jpeg_len = None
    while frame_count < STREAM_MAX_FRAMES and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        jpeg, encode_ms = capture_jpeg(sensor)
        if first_jpeg_len is None:
            first_jpeg_len = len(jpeg)
        part = ("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg)).encode()
        send_t0 = time.ticks_ms()
        send_all(client, part)
        send_all(client, jpeg)
        send_all(client, b"\r\n")
        send_ms = time.ticks_diff(time.ticks_ms(), send_t0)
        frame_count += 1
        if frame_count <= 3 or frame_count % 20 == 0:
            log("frame %d bytes=%d encode_ms=%d send_ms=%d" % (frame_count, len(jpeg), encode_ms, send_ms))
        if frame_count % 10 == 0:
            gc.collect()
    log("stream ended: frames=%d first_jpeg_len=%r" % (frame_count, first_jpeg_len))


wlan = network.WLAN(network.STA_IF)
for attempt in range(20):
    if wlan.isconnected():
        break
    log("waiting for WLAN link, attempt %d" % attempt)
    time.sleep_ms(300)
log("WLAN isconnected=%r ifconfig=%r" % (wlan.isconnected(), wlan.ifconfig()))

sensor = None
server = None
client = None
try:
    sensor = Sensor()
    sensor.reset()
    sensor.set_hmirror(True)
    sensor.set_vflip(True)
    sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT)
    # YUV420SP input makes Image.compress() emit a corrupted JPEG (confirmed
    # in wifi_test/jpeg_format_test.py: duplicated frame halves + color
    # shift, reproduced identically with no network involved at all).
    # RGB565 compresses correctly; see out_rgb565_fixed.jpg for reference.
    sensor.set_pixformat(Sensor.RGB565)
    MediaManager.init()
    sensor.run()
    for _ in range(5):
        sensor.snapshot()
    first, first_encode_ms = capture_jpeg(sensor)
    log("camera ready, first JPEG size=%d bytes encode_ms=%d" % (len(first), first_encode_ms))

    bind_addr = socket.getaddrinfo("0.0.0.0", PORT)[0][-1]
    for attempt in range(20):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(bind_addr)
            break
        except OSError as e:
            log("socket setup attempt %d failed: %r" % (attempt, e))
            try:
                server.close()
            except Exception:
                pass
            server = None
            time.sleep_ms(500)
    else:
        raise OSError("socket setup failed after retries")

    server.listen(2)
    server.setblocking(False)
    log("listening on port %d, open http://%s:%d/ in a browser" % (PORT, wlan.ifconfig()[0], PORT))

    poll = select.poll()
    poll.register(server, select.POLLIN)

    start = time.ticks_ms()
    served = 0
    MAX_CLIENTS = 5
    while served < MAX_CLIENTS:
        if time.ticks_diff(time.ticks_ms(), start) > TOTAL_TIMEOUT_MS:
            log("overall timeout, stopping")
            break
        events = poll.poll(1000)
        if not events:
            continue
        try:
            client, addr = server.accept()
        except OSError as e:
            log("accept EAGAIN/err: %r" % (e,))
            continue
        log("client connected: %r" % (addr,))
        try:
            path = read_path(client)
            log("path: %r" % (path,))
            if path == "/stream":
                stream_mjpeg(client, sensor)
            elif path == "/snapshot":
                jpeg, encode_ms = capture_jpeg(sensor)
                log("/snapshot bytes=%d encode_ms=%d" % (len(jpeg), encode_ms))
                send_jpeg(client, jpeg)
            else:
                send_html(client, INDEX_HTML)
            served += 1
        except OSError as e:
            log("client error: %r" % (e,))
        finally:
            client.close()
            client = None
            gc.collect()
finally:
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    if server is not None:
        try:
            server.close()
        except Exception:
            pass
    if sensor is not None:
        try:
            sensor.stop()
        except Exception as e:
            log("sensor.stop() err %r" % (e,))
    try:
        MediaManager.deinit()
    except Exception as e:
        log("MediaManager.deinit() err %r" % (e,))
    log("cleanup done")
