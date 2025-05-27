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
        # Read the config file and initialize the port, peer_num, peer_info, content_info from the config file
        config = json.load(open(config_file, "r"))
        self.hostname = config["hostname"]
        self.port = config["port"]
        self.peers = config["peers"]
        self.content_info = config["content_info"] # list of filenames
        self.peer_info = config["peer_info"]  # list of peer info, each peer info is a dict with hostname, port, content info

        # establish a socket according to the information
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #NOTE THAT THE SOCK_DGRAM will ensure your socket is UDP
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("", self.port)) #This is the only port you can use to receive
        self.server_socket.settimeout(1) # timeout value

        self.remain_threads = True
        self.cli()
        return

    def find_file(self, file_name):
        # returns a tuple of (hostname, port) of the peer that has the file
        for peer in self.peer_info:
            if file_name in peer["content_info"]:
                return (peer["hostname"], peer["port"])

    def load_file(self, file_name):
        # find which server has the file
        addr = self.find_file(file_name) # addr is a tuple (hostname, port)

        # establish a client socket for downloading file
        self.cl_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 

        # use a connect flag to determine if the file name is sent correctly
        connect_flag = False

        # Initiate three-way handshake and use a connect flag
        while not connect_flag:
            try:
                # handshake
                initial_message = json.dumps({"type": "SYN", "file_name": file_name}).encode()
                self.cl_socket.sendto(initial_message, addr)
                data, _ = self.cl_socket.recvfrom(BUFSIZE)
                response = json.loads(data.decode())

                if response.get("type") == "SYN-ACK":
                    connect_flag = True
                    # send ACK
                    ack_message = json.dumps({"type": "ACK"}).encode()
                    self.cl_socket.sendto(ack_message, addr)
            except socket.timeout:
                # handshake failed
                continue

        # the receiver keeps a record for which part has been acked

        # start receiving file

        # transmission complete, close socket

        # write the file


    def read_file(self, file_name):
        # read the file and return a list of packets of size PKTSIZE
        packets = []
        with open(file_name, 'rb') as f:
            while True:
                chunk = f.read(PKTSIZE)
                if not chunk:
                    break
                packets.append(chunk)
        return packets

    def transmit(self, file_name, addr):
        # create a udp socket for transmission
        tx_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx_socket.settimeout(TIMEOUT)  # set timeout for the socket

        # divide the file into several parts
        transmit_file = self.read_file(file_name)
        packet_num = len(transmit_file)

        # use socket to send packet number to the receiver
        print("sending packet num", packet_num, "to", addr)
        tx_socket.sendto(str(packet_num).encode(), addr)

        # use a transmit window to determine which file should be transmitted
        base = 0
        next_seq = 0
        timeout_status = [0] * packet_num # -1 = ACKed, 0 = not sent, >0 = last sent time
        acked = [False] * packet_num  # to keep track of which packets have been acknowledged
        lock = threading.Lock()  # lock for thread safety

        def transmit_thread():
            #Takes the transmit window and transmits every packet that is allowed to be transmitted
            nonlocal base, next_seq, timeout_status, acked
            while base < packet_num:
                with lock:
                    while next_seq < base + WINDOW_SIZE and next_seq < packet_num:
                        if timeout_status[next_seq] == 0:
                            packet = transmit_file[next_seq]
                            packet_index = next_seq.to_bytes(IDX_LENGTH, 'big')
                            tx_socket.sendto(packet_index + packet, addr)
                            timeout_status[next_seq] = time.time()  # record the time of sending
                        next_seq += 1

                    # check for timeouts and resend packets if necessary
                    for i in range(base, min(base + WINDOW_SIZE, packet_num)):
                        if timeout_status[i] > 0 and time.time() - timeout_status[i] > TIMEOUT:
                            # resend the packet if it has timed out
                            packet = transmit_file[i]
                            packet_index = i.to_bytes(IDX_LENGTH, 'big')
                            tx_socket.sendto(packet_index + packet, addr)
                            timeout_status[i] = time.time()

                time.sleep(0.1)  # sleep to avoid busy waiting

        def ack_thread():
            #Receives acknowledgement and updates the transmit window with sendable packets
            nonlocal base, next_seq, timeout_status, acked
            while base < packet_num:
                try:
                    ack_data, _ = tx_socket.recvfrom(BUFSIZE)
                    ack_idx = int.from_bytes(ack_data[:IDX_LENGTH], 'big')
                    with lock:
                        if not acked[ack_idx]:
                            acked[ack_idx] = True
                            timeout_status[ack_idx] = -1
                            if ack_idx == base:
                                # move the base forward if the ACK is for the base packet
                                while base < packet_num and acked[base]:
                                    base += 1
                                next_seq = max(next_seq, base)
                except socket.timeout:
                    continue

        #Create TX and RX threads and start doing it
        tx = threading.Thread(target=transmit_thread)
        ack = threading.Thread(target=ack_thread)
        tx.start()
        ack.start()
        tx.join()
        ack.join()

        # When done transmitting, close the threads.
        tx_socket.close()

    def listener(self): # listen to the socket to see if there's any transmission request
        while self.remain_threads:
            try:
                data, addr = self.server_socket.recvfrom(BUFSIZE)
                message = json.loads(data.decode())

                if message.get("type") == "SYN":
                    requested_file = message.get("file_name")

                    syn_ack_message = json.dumps({"type": "SYN-ACK"}).encode()
                    self.server_socket.sendto(syn_ack_message, addr)

                    # start transmission after receiving ACK
                    try:
                        ack_data, ack_addr = self.server_socket.recvfrom(BUFSIZE)
                        ack_message = json.loads(ack_data.decode())
                        if ack_message.get("type") == "ACK":
                            transmission_thread = threading.Thread(target=self.transmit, args=(requested_file, addr))
                            transmission_thread.start()

                    # ACK not received, continue waiting for ACK
                    except socket.timeout:
                        continue

            # no data received, continue listening
            except socket.timeout:
                continue

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