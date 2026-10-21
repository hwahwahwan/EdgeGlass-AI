import socket
import select
import time
import network
import gc
import os

PORT = 8070
MAX_REQUESTS = 4
TOTAL_TIMEOUT_MS = 60000
REQUEST_TIMEOUT_MS = 3000
MAX_REQUEST_BYTES = 4096


def log(msg):
    print("[HTTP]", msg)


def error_code(error):
    return getattr(error, "errno", error.args[0] if error.args else None)


def read_request(client):
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
                return bytes(request)
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)
        time.sleep_ms(10)
    raise ValueError("request header too large")


def build_body(counter, client_address):
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>K230D wifi_test</title></head><body>"
        "<h1>EdgeGlass-AI wifi_test HTTP server</h1>"
        "<p>request #%d</p><p>client: %s:%s</p>"
        "<p>uptime_ms: %d</p></body></html>"
    ) % (counter, client_address[0], client_address[1], time.ticks_ms())


def send_response(client, body_text):
    body = body_text.encode()
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "\r\n"
    ) % len(body)
    client.setblocking(True)
    client.settimeout(5)
    client.sendall(header.encode() + body)


wlan = network.WLAN(network.STA_IF)
for attempt in range(20):
    if wlan.isconnected():
        break
    log("waiting for WLAN link, attempt %d" % attempt)
    time.sleep_ms(300)
log("WLAN isconnected=%r ifconfig=%r" % (wlan.isconnected(), wlan.ifconfig()))

bind_addr = socket.getaddrinfo("0.0.0.0", PORT)[0][-1]
server = None
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

server.listen(5)
server.setblocking(False)
log("listening on port %d, open http://%s:%d/ in a browser" % (PORT, wlan.ifconfig()[0], PORT))

poll = select.poll()
poll.register(server, select.POLLIN)

start = time.ticks_ms()
counter = 0

try:
    while counter < MAX_REQUESTS:
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
            request = read_request(client)
            log("request head: %r" % (request[:120],))
            send_response(client, build_body(counter, addr))
            counter += 1
            log("response sent, counter=%d" % counter)
        except (OSError, ValueError) as e:
            log("request handling error: %r" % (e,))
        finally:
            client.close()
            gc.collect()
finally:
    poll.unregister(server)
    server.close()
    log("server closed, served=%d" % counter)
