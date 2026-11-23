"""Tiny HTTPS (CONNECT) proxy used to simulate network loss for StreamGrab tests.

Run the app with HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:8899 and this proxy in front of it:
  python tests/netsim.py            -> forwards traffic normally
Kill this process to simulate the connection dropping: every open transfer is cut and new
connections are refused, exactly like losing the network from the app's point of view.
"""
import socket
import threading
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def handle(c):
    try:
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = c.recv(4096)
            if not chunk:
                c.close()
                return
            head += chunk
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        method, target, _ = line.split(" ", 2)
        if method.upper() != "CONNECT":
            c.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            c.close()
            return
        host, port = target.rsplit(":", 1)
        u = socket.create_connection((host, int(port)), timeout=15)
        u.settimeout(None)
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        threading.Thread(target=pipe, args=(c, u), daemon=True).start()
        threading.Thread(target=pipe, args=(u, c), daemon=True).start()
    except Exception:
        try:
            c.close()
        except OSError:
            pass


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", PORT))
srv.listen(64)
print(f"netsim proxy on 127.0.0.1:{PORT}", flush=True)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
