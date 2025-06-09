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
                thread = threading.Thread(target=self.persistent_handler, args=(connection_socket,))
                thread.start()
            except Exception as e:
                print(f"[ERROR] Accept failed: {e}")
                self.remain_threads = False
                self.http_socket.close()
                break

    def persistent_handler(self, connection_socket):
        while True:
            try:
                msg_string = connection_socket.recv(BUFSIZE).decode()
                if not msg_string:
                    break

                keep_alive = self.response(msg_string, connection_socket)
                if not keep_alive:
                    break
            except Exception as e:
                print(f"[ERROR] In persistent handler: {e}")
                break
        connection_socket.close()

    def response(self, msg_string, connection_socket):
        try:
            message = msg_string.strip().split("\r\n")
            print(f"[DEBUG] Parsed message: {message}")
            request_line = message[0]
            headers = self.eval_commands(message[1:])
            conn_type = headers.get("Connection", "close").lower()
            keep_alive = conn_type == "keep-alive"

            print(f"[DEBUG] Request Line: {request_line}")
            method, uri, http_version = request_line.split()

            # only allow GET
            if method != "GET":
                print("[DEBUG] Method not allowed, sending 405 response.")
                response = f"{http_version} 405 Method Not Allowed\r\nConnection: close\r\n\r\n"
                connection_socket.sendall(response.encode())
                return False

            # parse the URI
            file_idx = uri.lstrip("/")

            # handle 404 requests
            if file_idx not in self.content:
                print(f"[DEBUG] File {file_idx} not found, sending 404 response.")
                response = self.generate_response_404(http_version)
                connection_socket.sendall(response.encode())
                return False

            file_info = self.content[file_idx]
            # handle 403 requests
            if "confidential" in file_info["path"]:
                print(f"[DEBUG] File {file_idx} is confidential, sending 403 response.")
                response = self.generate_response_403(http_version)
                connection_socket.sendall(response.encode())
                return False

            # handle 200 or 206 responses based on file size and range header
            is_large_file = file_info["size"] > LARGEST_CONTENT_SIZE
            if is_large_file:
                print(f"[DEBUG] File {file_idx} is large ({file_info['size']} bytes), handling with range requests.")
                if "Range" in headers:
                    print(f"[DEBUG] Range request for {file_idx}, sending 206 response.")
                    response = self.generate_response_206(http_version, file_idx, file_info["type"], headers["Range"], keep_alive)
                else:
                    print(f"[DEBUG] Large file request with no range, forcing 206 response with 5 MB limit.")
                    response = self.generate_response_206(http_version, file_idx, file_info["type"], "bytes=0-", keep_alive)
            else:
                print(f"[DEBUG] Regular request for {file_idx}, sending 200 response.")
                response = self.generate_response_200(http_version, file_idx, file_info["type"], keep_alive)

            connection_socket.sendall(response)
            print(f"[DEBUG] Response sent for {file_idx}. Keep-alive: {keep_alive}")
            return keep_alive

        except Exception as e:
            print(f"[ERROR] An error occurred while processing the request: {e}")
            response = f"{http_version} 500 Internal Server Error\r\nConnection: close\r\n\r\n"
            connection_socket.sendall(response.encode())
            return False

    def generate_response_404(self, http_version):
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

    def generate_response_403(self, http_version):
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

    def generate_response_200(self, http_version, file_idx, file_type, keep_alive):
        file_path = self.content[file_idx]["path"]
        file_size = self.content[file_idx]["size"]
        content_type = self.generate_content_type(file_type)

        try:
            with open(file_path, "rb") as file:
                file_content = file.read()

            last_modified = datetime.datetime.utcfromtimestamp(os.path.getmtime(file_path)).strftime('%a, %d %b %Y %H:%M:%S GMT')

            headers = [
                f"{http_version} 200 OK",
                f"Content-Type: {content_type}",
                f"Content-Length: {file_size}",
                f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
                f"Last-Modified: {last_modified}",
                f"Connection: {'keep-alive' if keep_alive else 'close'}",
                "Accept-Ranges: bytes",
                "", ""
            ]
            response = "\r\n".join(headers).encode() + file_content
            return response

        except Exception as e:
            print(f"[ERROR] Failed to read file {file_idx}: {e}")
            response = f"{http_version} 500 Internal Server Error\r\n\r\n".encode()
            return response

    def generate_response_206(self, http_version, file_idx, file_type, command_parameters, keep_alive):
        file_path = self.content[file_idx]["path"]
        file_size = self.content[file_idx]["size"]
        content_type = self.generate_content_type(file_type)

        try:
            range_header = command_parameters.split("=")[1].strip()
            if "-" not in range_header:
                raise ValueError("Invalid range format")
            
            parts = range_header.split("-", 1)
            start = int(parts[0]) if parts[0] else 0
            if parts[1]:
                end = int(parts[1])
            else:
                end = min(start + LARGEST_CONTENT_SIZE - 1, file_size - 1)

            end = min(end, file_size - 1)

            if start < 0 or start > end or start >= file_size:
                raise ValueError("Invalid range")

            with open(file_path, "rb") as file:
                file.seek(start)
                file_content = file.read(end - start + 1)

            last_modified = datetime.datetime.utcfromtimestamp(os.path.getmtime(file_path)).strftime('%a, %d %b %Y %H:%M:%S GMT')

            headers = [
                f"{http_version} 206 Partial Content",
                f"Content-Type: {content_type}",
                f"Content-Length: {len(file_content)}",
                f"Content-Range: bytes {start}-{end}/{file_size}",
                "Accept-Ranges: bytes",
                f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
                f"Last-Modified: {last_modified}",
                f"Connection: {'keep-alive' if keep_alive else 'close'}",
                "", ""
            ]
            response = "\r\n".join(headers).encode() + file_content
            return response

        except Exception as e:
            print(f"[ERROR] Failed to process range request for {file_idx}: {e}")
            response = f"{http_version} 416 Range Not Satisfiable\r\n\r\n".encode()
            return response

    def generate_content_type(self, file_type):
        content_types = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "ogg": "video/webm",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "txt": "text/plain",
            "css": "text/css",
            "html": "text/html",
            "htm": "text/html",
            "gif": "image/gif",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "js": "application/javascript",
            "json": "application/json",
            "pdf": "application/pdf",
        }
        return content_types.get(file_type, "application/octet-stream")

    def eval_commands(self, commands):
        command_dict = {}
        for item in commands:
            if ':' not in item or not item.strip():
                continue
            item = item.rstrip()
            splitted_item = item.split(":", 1)
            if len(splitted_item) == 2:
                command_dict[splitted_item[0]] = splitted_item[1].strip()
        return command_dict

if __name__ == "__main__":
    port_id = sys.argv[1]
    Vod_Server(int(port_id))
