import socket
import threading
import queue
import time

class Tunnel:

    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 10000
        self.server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host,self.port))
        self.server.listen(5)
        self.client_recv = queue.Queue()
        self.client_send = queue.Queue()


    def handel_request(self):
        try:
            while True:
                conn , addr = self.server.accept()
                print(f"recevied client from {addr[0]}")
                
                data = conn.recv(2024)
                link = data.decode().split()[1]
                print(link)

                if link == "/register":
                    handel_tunnel = threading.Thread(target = self.handel_tunnel , args = (conn,) , daemon=True)
                    handel_tunnel.start()
                else:
                    handel_client = threading.Thread(target = self.handel_client , args=(conn ,data) , daemon=True)
                    handel_client.start()

        except Exception as e:
            print("server error {e}")
        finally:
            self.server.close()




    def handel_tunnel(self,conn):

        send_tunnel="HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: keep-alive\r\n\r\n"
        conn.sendall(send_tunnel.encode())
        send_tunnel= b"tunnel register"
        conn.sendall(send_tunnel)
        time.sleep(1)
        while True:
            continue

    

    def handel_client(self, conn , data):
        pass




if __name__=="__main__":
    tunnel = Tunnel()
    tunnel.handel_request()

    