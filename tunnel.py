# server.py
import socket
import threading
import queue
import time

class TunnelServer:
    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 10000
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)

        # Support multiple tunnels (list of tunnel sessions)
        self.tunnels = []
        self.tunnels_lock = threading.Lock()

        # Round robin index
        self.tunnel_index = 0

        # Start health check thread
        threading.Thread(target=self.health_check_tunnels, daemon=True).start()

    def handle_request(self):
        print(f"[Server] Listening on {self.host}:{self.port}")
        try:
            while True:
                conn, addr = self.server.accept()
                print(f"[Server] Connection from {addr}")

                threading.Thread(target=self.dispatch_connection, args=(conn,), daemon=True).start()
        except Exception as e:
            print(f"[Server error]: {e}")
        finally:
            self.server.close()

    def dispatch_connection(self, conn):
        try:
            data = conn.recv(1024)
            if not data:
                conn.close()
                return

            first_line = data.decode(errors='ignore').split()
            if len(first_line) < 2:
                conn.close()
                return

            path = first_line[1]
            print(path)
            if path == "/register":
                self.handle_tunnel(conn)
            else:
                self.handle_client(conn, data)
        except Exception as e:
            print(f"[Dispatch error]: {e}")
            conn.close()

    def handle_tunnel(self, conn):
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: keep-alive\r\n\r\nTunnel registered\n")

            # Register tunnel
            send_queue = queue.Queue()
            recv_queue = queue.Queue()

            with self.tunnels_lock:
                self.tunnels.append({'conn': conn, 'send_q': send_queue, 'recv_q': recv_queue})
                print(f"[Server] Tunnel registered. Total tunnels: {len(self.tunnels)}")

            while True:
                # Wait for request from user
                request_data = send_queue.get()

                # Send request to tunnel client
                conn.sendall(request_data)

                # Receive full response from tunnel client
                full_response = self.recv_full_http_response(conn)

                # Put response into queue to send back to user
                recv_queue.put(full_response)

        except Exception as e:
            print(f"[Tunnel error]: {e}")

        finally:
            self.remove_tunnel(conn)
            conn.close()

    def get_next_tunnel(self):
        """Round-robin tunnel selector"""
        with self.tunnels_lock:
            if not self.tunnels:
                return None
            tunnel = self.tunnels[self.tunnel_index % len(self.tunnels)]
            self.tunnel_index = (self.tunnel_index + 1) % len(self.tunnels)
            return tunnel

    def handle_client(self, conn, initial_data):
        try:
            tunnel = None
            max_wait = 5  # seconds
            waited = 0
            interval = 0.1  # check every 100 ms

            while waited < max_wait:
                tunnel = self.get_next_tunnel()
                if tunnel:
                    break
                time.sleep(interval)
                waited += interval

            if tunnel is None:
                # No tunnel available after waiting, send error
                error_message = (
                    "HTTP/1.1 503 Service Unavailable\r\n"
                    "Content-Type: text/plain\r\n"
                    "Content-Length: 18\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    "No tunnel is open"
                ).encode()
                conn.sendall(error_message)
                return

            # Send user request to tunnel
            tunnel['send_q'].put(initial_data)

            # Get response from tunnel
            response = tunnel['recv_q'].get()

            # Send response back to user
            conn.sendall(response)

        except Exception as e:
            print(f"[Client error]: {e}")

        finally:
            conn.close()

    def recv_full_http_response(self, conn):
        """
        Receive full HTTP response from tunnel client (headers + body)
        Handles images, videos, etc. properly
        """
        buffer = b''
        headers_done = False
        content_length = None

        # Step 1: Read headers
        while not headers_done:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buffer += chunk
            if b'\r\n\r\n' in buffer:
                headers_done = True

        if not headers_done:
            return buffer  # Return whatever we got

        headers, body = buffer.split(b'\r\n\r\n', 1)

        # Step 2: Parse Content-Length (if present)
        for line in headers.split(b'\r\n'):
            if b'Content-Length:' in line:
                try:
                    content_length = int(line.split(b':')[1].strip())
                except ValueError:
                    content_length = None
                break

        # Step 3: Read body fully
        while content_length is not None and len(body) < content_length:
            chunk = conn.recv(4096)
            if not chunk:
                break
            body += chunk

        full_response = headers + b'\r\n\r\n' + body
        return full_response

    def health_check_tunnels(self):
        """Periodically check and remove dead tunnels"""
        while True:
            time.sleep(5)  # check every 5 seconds
            with self.tunnels_lock:
                to_remove = []
                for tunnel in self.tunnels:
                    conn = tunnel['conn']
                    try:
                        conn.settimeout(0.1)
                        conn.send(b'')  # Send empty bytes to check
                        conn.settimeout(None)
                    except:
                        to_remove.append(conn)
                for dead_conn in to_remove:
                    print("[HealthCheck] Removing dead tunnel")
                    self.remove_tunnel(dead_conn)

    def remove_tunnel(self, conn):
        """Safely remove tunnel"""
        with self.tunnels_lock:
            self.tunnels = [t for t in self.tunnels if t['conn'] != conn]
            print(f"[Server] Tunnel removed. Total tunnels: {len(self.tunnels)}")

if __name__ == "__main__":
    server = TunnelServer()
    server.handle_request()
