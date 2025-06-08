import socket, sys
import datetime
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
        
        # listen to the http socket
        self.listen()
        pass

    def load_contents(self, dir):
        #Create a list of files and stuff that you have
        return

    def listen(self):
        while self.remain_threads:
            connection_socket, client_address = self.http_socket.accept()
            msg_string = connection_socket.recv(BUFSIZE).decode()
            
            #Do stuff here
        return
    
    def response(self, msg_string, connection_socket):
        #Do based on the situation if the files exist, do not exist or are unable to respond due to confidentiality
        return
    
    def generate_response_404(self, http_version, connection_socket):
        #Generate Response and Send
        
        return response

    def generate_response_403(self, http_version, connection_socket):
        #Generate Response and Send
        
        return response
    
    def generate_response_200(self, http_version, file_idx, file_type, connection_socket):
        #Generate Response and Send
        
        return response

    def generate_response_206(self, http_version, file_idx, file_type, command_parameters, connection_socket):
        #Generate Response and Send
        
        return response

    def generate_content_type(self, file_type):
        #Generate Headers
        return ""

    def eval_commands(self, commands):
        command_dict = {}
        for item in commands[1:]:
            item = item.rstrip()
            splitted_item = item.split(":")
            command_dict[splitted_item[0]] = splitted_item[1].strip()
        return command_dict

if __name__ == "__main__":
    Vod_Server(int(sys.argv[1]))