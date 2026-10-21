import socket
import select
import time
import network

PORT = 8090
MAX_CONN = 3
TOTAL_TIMEOUT_MS = 60000


def log(msg):
    print("[TCP]", msg)


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
        log("socket/setsockopt/bind attempt %d failed: %r" % (attempt, e))
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
log("listening on port %d" % PORT)

poll = select.poll()
poll.register(server, select.POLLIN)

start = time.ticks_ms()
handled = 0

try:
    while handled < MAX_CONN:
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
        client.setblocking(False)
        cpoll = select.poll()
        cpoll.register(client, select.POLLIN)
        deadline = time.ticks_add(time.ticks_ms(), 10000)
        data = b""
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            cev = cpoll.poll(500)
            if cev:
                try:
                    chunk = client.recv(256)
                except OSError as e:
                    log("recv err: %r" % (e,))
                    break
                if chunk:
                    data += chunk
                    log("received: %r" % (chunk,))
                    if data.endswith(b"\n") or data.endswith(b"end"):
                        break
                else:
                    log("peer closed (empty recv)")
                    break
        reply = b"ECHO:" + data
        try:
            client.setblocking(True)
            client.settimeout(5)
            client.send(reply)
            log("sent reply: %r" % (reply,))
        except OSError as e:
            log("send err: %r" % (e,))
        client.close()
        cpoll.unregister(client)
        handled += 1
finally:
    poll.unregister(server)
    server.close()
    log("server closed, handled=%d" % handled)
