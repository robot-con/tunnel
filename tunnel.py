import socket
import threading
import queue


class Tunnel:
    def __init__(self, host="0.0.0.0", port=10000):
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(20)

        self.tunnel_conn = None
        self.lock = threading.Lock()
        self.client_queues = queue.Queue()  # Queue of (request_data, response_queue)

    def start(self):
        print(f"Tunnel server listening on {self.host}:{self.port}")
        try:
            while True:
                conn, addr = self.server.accept()
                print(f"Connection received from {addr}")
                threading.Thread(target=self.handle_connection, args=(conn,), daemon=True).start()
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.server.close()

    def handle_connection(self, conn):
        try:
            data = conn.recv(4096)
            if not data:
                conn.close()
                return

            request_line = data.decode(errors="ignore").split("\r\n")[0]
            if not request_line:
                conn.close()
                return

            path = request_line.split()[1]
            if path == "/register":
                threading.Thread(target=self.handle_tunnel, args=(conn,), daemon=True).start()
            else:
                threading.Thread(target=self.handle_client, args=(conn, data), daemon=True).start()
        except Exception as e:
            print(f"Handle connection error: {e}")
            conn.close()

    def handle_tunnel(self, conn):
        print("[Tunnel] Registered")
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: keep-alive\r\n\r\n Tunnel connected\n")
            self.tunnel_conn = conn

            while True:
                req_data, response_queue = self.client_queues.get()

                # Send request to the tunnel client
                conn.sendall(req_data)

                # Read full response (headers + body) and forward to response_queue
                response = b""
                while b"\r\n\r\n" not in response:
                    chunk = conn.recv(1024)
                    if not chunk:
                        raise Exception("Tunnel disconnected while reading headers")
                    response += chunk

                headers, body_start = response.split(b"\r\n\r\n", 1)
                response_queue.put(headers + b"\r\n\r\n")

                headers_text = headers.decode(errors="ignore").lower()
                if "transfer-encoding: chunked" in headers_text:
                    # Handle chunked response
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        response_queue.put(chunk)
                        if b"0\r\n\r\n" in chunk:
                            break
                else:
                    # Handle Content-Length
                    content_length = 0
                    for line in headers_text.split("\r\n"):
                        if line.startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    received = len(body_start)
                    if body_start:
                        response_queue.put(body_start)

                    while received < content_length:
                        chunk = conn.recv(min(8192, content_length - received))
                        if not chunk:
                            break
                        received += len(chunk)
                        response_queue.put(chunk)

                response_queue.put(None)  # End of response
        except Exception as e:
            print(f"[Tunnel] Error: {e}")
        finally:
            self.tunnel_conn = None
            conn.close()

    def handle_client(self, conn, initial_data):
        print("[Client] Handling request")
        response_queue = queue.Queue()
        try:
            if not self.tunnel_conn:
                conn.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/plain\r\n\r\nTunnel Not Connected")
                conn.close()
                return

            # Send to tunnel and wait for response
            self.client_queues.put((initial_data, response_queue))

            while True:
                chunk = response_queue.get()
                if chunk is None:
                    break
                conn.sendall(chunk)
        except Exception as e:
            print(f"[Client] Error: {e}")
        finally:
            conn.close()


if __name__ == "__main__":
    tunnel = Tunnel()
    tunnel.start()
