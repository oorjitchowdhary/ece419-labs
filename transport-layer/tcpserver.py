import socket, sys
import json
import time
import threading

BUFSIZE = 10202  # size of receiving buffer
PKTSIZE = 10200  # number of bytes in a packet
WINDOW_SIZE = 16
IDX_LENGTH = 2 # 2 bytes of packet index
TIMEOUT = 0.5   # timeout time

class Server():
    def __init__(self, config_file):
        #Read the config file and initialize the port, peer_num, peer_info, content_info from the config file

        # establish a socket according to the information
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #NOTE THAT THE SOCK_DGRAM will ensure your socket is UDP
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("", self.port)) #This is the only port you can use to receive
        
        self.server_socket.settimeout(1)   # timeout value

        self.remain_threads = True
        self.cli()
        return
    
    def find_file(self, file_name):
        #A function to find the peer with the file you want!

    
    def load_file(self, file_name):
        # find which server has the file
        # establish a client socket for downloading file
        self.cl_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        
        # use a connect flag to determine if the file name is sent correctly
        
        #Initiate three-way handshake and use a connect flag
        
        while not connect_flag:
            try:
                # handshake
            except socket.timeout:
                # handshake failed
      
        # the receiver keeps a record for which part has been acked

        # start receiving file

        # transmission complete, close socket

        # write the file
        
    def read_file(self, file_name):
        #You can write a function that takes the file to be transmitted and converts into chunks of packet_size
        return transmit_file

    def transmit(self, file_name, addr):
        # create a udp socket for transmission
        # divide the file into several parts
        #transmit_file = self.read_file(file_name)
        #packet_num = len(transmit_file)
        # use socket to send packet number to the receiver
        #ack = 0
        #print("sending packet num", packet_num, "to", addr)
        tx_socket.sendto(str(packet_num).encode(), addr)
        try:
            #Receive ACK from the same tx_socket and increment window
        except socket.timeout:
            pass
        # use a transmit window to determine which file should be transmitted

        # use a time-out array to record which file is time-out and need to be transmitted again
        # -1 indicates received, 0 indicates not transmitted, positive numbers means the time of transmission
        
        def transmit_thread():
            #Takes the transmit window and transmits every packet that is allowed to be transmitted
            return
        
        def ack_thread():
            #Receives acknowledgement and updates the transmit window with sendable packets
        
        #Create TX and RX threads and start doing it

        #When done transmitting, close the threads.

    def listener(self): # listen to the socket to see if there's any transmission request
        #Do any initializations that you want
        while self.remain_threads:
            file_name = ""
            try:
                file_name, addr = self.server_socket.recvfrom(BUFSIZE)
                #Receive the file name and requesting address from the UDP
            except socket.timeout:
                pass
            
            if file_name == "":
                pass
            else:   # start transmission
                ;#Create a transmit thread (HINT : you can have a large array of transmit threads if you want) and start it
                
        return
    
    def cli(self):  # cli interface for input of the file name
        listen_thread = threading.Thread(target=self.listener)
        listen_thread.start()

        while self.remain_threads:
            command_line = input()
            if command_line == "kill":  # for debugging purpose
                #Do the kill stuff
                return
            #Otherwise it is a file name!
        #Exit stuff if you have some?
        return


if __name__ == "__main__":
    server = Server(sys.argv[1])