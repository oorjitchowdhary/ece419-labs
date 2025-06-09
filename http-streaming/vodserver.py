import socket, sys
import datetime
import threading
import os

BUFSIZE = 1024
LARGEST_CONTENT_SIZE = 5242880

class Vod_Server():
    def __init__(self, port_id):
        # create an HTTP port to listen to
        self.http_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.http_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.http_socket.bind(("", port_id))
        self.http_socket.listen(10000)
        self.remain_threads = True

        # load all contents in the buffer
        self.content = self.load_contents("./content")
        print(f"[DEBUG] Loaded {len(self.content)} files from content directory.")
        print(f"[DEBUG] Content: {self.content}")

        # listen to the http socket
        self.listen()

    def load_contents(self, dir):
        content = {}
        for root, _, files in os.walk(dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dir)  # relative to content/
                filename, file_extension = os.path.splitext(rel_path)
                content[filename + file_extension] = {
                    "path": full_path,
                    "type": file_extension[1:],  # remove dot
                    "size": os.path.getsize(full_path)
                }
        return content

    def listen(self):
        print(f"[DEBUG] Listening on port {self.http_socket.getsockname()[1]}...")

        while self.remain_threads:
            try:
                connection_socket, client_address = self.http_socket.accept()
                msg_string = connection_socket.recv(BUFSIZE).decode()
                if not msg_string:
                    print("[DEBUG] No message received, closing connection.")
                    connection_socket.close()
                    continue

                print(f"[DEBUG] Received message: {msg_string.strip()}")

                thread = threading.Thread(target=self.response, args=(msg_string, connection_socket))
                thread.start()

            except Exception as e:
                print(f"[ERROR] An error occurred: {e}")
                self.remain_threads = False
                self.http_socket.close()
                break

        return

    def response(self, msg_string, connection_socket):
        #Do based on the situation if the files exist, do not exist or are unable to respond due to confidentiality
        try:
            message = msg_string.strip().split("\r\n")
            print(f"[DEBUG] Parsed message: {message}")
            request_line = message[0]
            headers = self.eval_commands(message[1:])

            print(f"[DEBUG] Request Line: {request_line}")
            method, uri, http_version = request_line.split()

            # only allow GET
            if method != "GET":
                print("[DEBUG] Method not allowed, sending 405 response.")
                response = f"{http_version} 405 Method Not Allowed\r\n\r\n"
                connection_socket.sendall(response.encode())
                connection_socket.close()
                return

            # parse the URI
            file_idx = uri.lstrip("/")

            if file_idx not in self.content:
                print(f"[DEBUG] File {file_idx} not found, sending 404 response.")
                response = self.generate_response_404(http_version, connection_socket)
                connection_socket.sendall(response.encode())
                connection_socket.close()
                return

            file_info = self.content[file_idx]
            if "confidential" in file_info["path"]:
                print(f"[DEBUG] File {file_idx} is confidential, sending 403 response.")
                response = self.generate_response_403(http_version, connection_socket)
                connection_socket.sendall(response.encode())
                connection_socket.close()
                return

            # check for range requests
            if "Range" in headers:
                print(f"[DEBUG] Range request detected for {file_idx}, sending 206 response.")
                response = self.generate_response_206(http_version, file_idx, file_info["type"], headers["Range"], connection_socket)
                connection_socket.sendall(response.encode())
                connection_socket.close()
            else:
                print(f"[DEBUG] Regular request for {file_idx}, sending 200 response.")
                response = self.generate_response_200(http_version, file_idx, file_info["type"], connection_socket)
                connection_socket.sendall(response.encode())
                connection_socket.close()

            print(f"[DEBUG] Response sent for {file_idx}.")

        except Exception as e:
            print(f"[ERROR] An error occurred while processing the request: {e}")
            response = f"HTTP/1.1 500 Internal Server Error\r\n\r\n"
            connection_socket.sendall(response.encode())
            connection_socket.close()


    def generate_response_404(self, http_version, connection_socket):
        not_found_page = "<html><body><h1>404 Not Found</h1></body></html>"
        headers = [
            f"{http_version} 404 Not Found",
            "Content-Type: text/html",
            f"Content-Length: {len(not_found_page)}",
            f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
            "Connection: close",
            "\r\n"
        ]
        response = "\r\n".join(headers) + not_found_page
        return response

    def generate_response_403(self, http_version, connection_socket):
        forbidden_page = "<html><body><h1>403 Forbidden</h1></body></html>"
        headers = [
            f"{http_version} 403 Forbidden",
            "Content-Type: text/html",
            f"Content-Length: {len(forbidden_page)}",
            f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
            "Connection: close",
            "\r\n"
        ]
        response = "\r\n".join(headers) + forbidden_page
        return response

    def generate_response_200(self, http_version, file_idx, file_type, connection_socket):
        #Generate Response and Send
        
        return response

    def generate_response_206(self, http_version, file_idx, file_type, command_parameters, connection_socket):
        #Generate Response and Send
        
        return response

    def generate_content_type(self, file_type):
        content_types = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "txt": "text/plain",
            "html": "text/html",
            "json": "application/json",
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }
        return content_types.get(file_type, "application/octet-stream")

    def eval_commands(self, commands):
        command_dict = {}
        for item in commands[1:]:
            item = item.rstrip()
            splitted_item = item.split(":")
            command_dict[splitted_item[0]] = splitted_item[1].strip()
        return command_dict

if __name__ == "__main__":
    port_id = sys.argv[1]
    Vod_Server(int(port_id))
