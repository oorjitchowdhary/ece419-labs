import socket, sys
import json
import time
import threading
import uuid

BUFSIZE = 7402
PKTSIZE = 7400
# BUFSIZE = 10202  # size of receiving buffer
# PKTSIZE = 10200  # number of bytes in a packet
WINDOW_SIZE = 16
IDX_LENGTH = 2 # 2 bytes of packet index
TIMEOUT = 0.5   # timeout time

class Server():
    def __init__(self, config_file):
        # parse server configuration from the config file
        print("[DEBUG] Loading config:", config_file)
        try:
            config = json.load(open(config_file, "r"))
        except Exception as e:
            print(f"[DEBUG] Failed to load config file {config_file}: {e}")
            sys.exit(1)

        self.hostname = config["hostname"]
        self.port = config["port"]
        self.peers = config["peers"]
        self.content_info = config["content_info"] # list of filenames
        self.peer_info = config["peer_info"]  # list of peer info, each peer info is a dict with hostname, port, content info

        # establish a socket according to the information
        print(f"[DEBUG] Starting server on {self.hostname}:{self.port}")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #NOTE THAT THE SOCK_DGRAM will ensure your socket is UDP
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("", self.port)) #This is the only port you can use to receive
        self.server_socket.settimeout(1) # timeout value

        # track sessions on the server
        self.sessions = {} # session_id -> session info

        # initialize the server
        self.remain_threads = True
        self.cli()


    def find_file(self, file_name):
        # returns a tuple of (hostname, port) of the peer that has the file
        print(f"[DEBUG] Looking for file '{file_name}' in peer list")

        for peer in self.peer_info:
            if file_name in peer["content_info"]:
                print(f"[DEBUG] Found file on peer {peer['hostname']}:{peer['port']}")
                return (peer["hostname"], peer["port"])

        print(f"[DEBUG] File '{file_name}' not found on any peer")
        return None


    def read_file(self, file_name):
        # read the file and return a list of packets of size PKTSIZE
        print(f"[DEBUG] Reading file: {file_name}")
        packets = []
        with open(file_name, 'rb') as f:
            while True:
                chunk = f.read(PKTSIZE)
                if not chunk:
                    break
                packets.append(chunk)
        print(f"[DEBUG] Read complete. Total packets: {len(packets)}")
        return packets


    def receive(self, file_name):
        print(f"[DEBUG] Starting to receive file: {file_name}")

        addr = self.find_file(file_name)  # addr is a tuple (hostname, port)
        if not addr:
            print(f"[DEBUG] No peer found for file: {file_name}")
            return

        session_id = uuid.uuid4().bytes  # generate a unique session ID
        filename_bytes = file_name.encode()

        # create session entry (receiver side)
        self.sessions[session_id] = {
            "addr": addr,
            "total_packets": 0,  # will be set after receiving SYN-ACK
            "received": [],  # to keep track of received packets
            "lock": threading.Lock(),  # lock for thread safety
            "complete": False,  # set to True when all packets are received
        }

        # send SYN packet
        syn_packet = bytearray()
        syn_packet.append(0x00)  # SYN packet type
        syn_packet.extend(session_id)  # append session ID
        syn_packet.append(len(filename_bytes))  # append length of filename
        syn_packet.extend(filename_bytes)  # append filename
        self.server_socket.sendto(syn_packet, addr)
        print(f"[DEBUG] Sent SYN to {addr} for file '{file_name}' with session ID {session_id.hex()}")


    def transmit(self, file_name, addr, session_id):
        print(f"[DEBUG] Starting transmission to {addr} for file {file_name}")
        tx_socket = self.server_socket  # reuse the server socket for transmission


    def handle_syn(self, packet, addr):
        session_id = packet[:16] # first 16 bytes are the session ID
        filename_length = packet[16] # next byte is the length of the filename
        filename = packet[17:17 + filename_length].decode() # next bytes are the filename

        print(f"[DEBUG] Received SYN from {addr} for file '{filename}' with session ID {session_id.hex()}")

        total_packets = len(self.read_file(filename))  # get the total number of packets for the file
        print(f"[DEBUG] Total packets for file '{filename}': {total_packets}")

        # create a session entry (sender side)
        self.sessions[session_id] = {
            "filename": filename,
            "addr": addr,
            "total_packets": total_packets,
            "base": 0,
            "next_seq": 0,
            "timeout_status": [0] * total_packets,  # -1 = ACKed, 0 = not sent, >0 = last sent time
            "acked": [False] * total_packets,  # to keep track of which packets have been acknowledged
            "lock": threading.Lock(),  # lock for thread safety
            "ready": False  # set to True after ACK
        }

        # send SYN-ACK response
        response = bytearray()
        response.append(0x01)  # SYN-ACK packet type
        response.extend(session_id)  # append session ID
        response.extend(total_packets.to_bytes(2, 'big'))  # append total packets count
        self.server_socket.sendto(response, addr)
        print(f"[DEBUG] Sent SYN-ACK to {addr} for session ID {session_id.hex()}")


    def handle_syn_ack(self, packet, addr):
        session_id = packet[:16] # first 16 bytes are the session ID
        total_packets = int.from_bytes(packet[16:18], 'big')  # next 2 bytes are the total packets count

        print(f"[DEBUG] Received SYN-ACK from {addr} for session ID {session_id.hex()} with total packets {total_packets}")

        # update session entry (receiver side)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session["total_packets"] = total_packets
            session["received"] = [None] * total_packets

        # send ACK response
        response = bytearray()
        response.append(0x02)  # ACK packet type
        response.extend(session_id)  # append session ID
        self.server_socket.sendto(response, addr)
        print(f"[DEBUG] Sent ACK to {addr} for session ID {session_id.hex()}")


    def handle_ack(self, packet, addr):
        session_id = packet[:16]

        print(f"[DEBUG] Received ACK from {addr} for session ID {session_id.hex()}")
        if session_id not in self.sessions:
            print(f"[DEBUG] Session ID {session_id.hex()} not found in sessions.")
            return

        session = self.sessions[session_id]

        # check if sender side and mark as ready
        if "ready" in session:
            with session["lock"]:
                session["ready"] = True
                print(f"[DEBUG] Session {session_id.hex()} is now ready for transmission.")

        threading.Thread(target=self.transmit, args=(session["filename"], addr, session_id)).start()
        print(f"[DEBUG] Transmission thread started for session ID {session_id.hex()}")


    def listener(self): # listen to the socket to see if there's any transmission request
        print(f"[DEBUG] Listening on port {self.port}")

        while self.remain_threads:
            try:
                packet, addr = self.server_socket.recvfrom(BUFSIZE)
                if not packet:
                    print("[DEBUG] No data received, continuing to listen.")
                    continue

                pkt_type = packet[0] # first byte indicates the type of packet
                if pkt_type == 0x00: # SYN packet (received by server)
                    self.handle_syn(packet[1:], addr)
                elif pkt_type == 0x01: # SYN-ACK packet (received by client)
                    self.handle_syn_ack(packet[1:], addr)
                elif pkt_type == 0x02: # ACK packet (received by server)
                    self.handle_ack(packet[1:], addr)
                elif pkt_type == 0x03: # Data packet (received by client)
                    self.handle_data(packet[1:], addr)
                elif pkt_type == 0x04: # DATA-ACK packet (received by server)
                    self.handle_data_ack(packet[1:], addr)
                elif pkt_type == 0x05: # FIN packet
                    self.handle_fin(packet[1:], addr)
                elif pkt_type == 0x06: # FIN-ACK packet
                    self.handle_fin_ack(packet[1:], addr)
                else:
                    print(f"[DEBUG] Unknown packet type {pkt_type} received from {addr}")

            # no data received, continue listening
            except socket.timeout:
                continue

        print("[DEBUG] Listener thread exiting.")


    def cli(self):  # cli interface for input of the file name
        listen_thread = threading.Thread(target=self.listener)
        listen_thread.start()

        while self.remain_threads:
            try:
                command_line = input()
                if command_line == "kill":
                    print("[DEBUG] Shutting down server.")
                    self.remain_threads = False
                    self.server_socket.close()
                    listen_thread.join()
                    print("[DEBUG] Server shutdown complete.")
                    break

                # otherwise input is a file name to load
                print(f"[DEBUG] CLI input received: {command_line}")
                self.receive(command_line.strip())

            except EOFError:
                print("[DEBUG] EOFError encountered. Exiting CLI.")
                self.remain_threads = False
                self.server_socket.close()
                listen_thread.join()
                break


if __name__ == "__main__":
    print(f"[DEBUG] Starting server with config: {sys.argv[1]}")
    server = Server(sys.argv[1])


        # # use socket to send packet number to the receiver
        # print("sending packet num", packet_num, "to", addr)
        # tx_socket.sendto(str(packet_num).encode(), addr)

        # # use a transmit window to determine which file should be transmitted
        # base = 0
        # next_seq = 0
        # timeout_status = [0] * packet_num # -1 = ACKed, 0 = not sent, >0 = last sent time
        # acked = [False] * packet_num  # to keep track of which packets have been acknowledged
        # lock = threading.Lock()  # lock for thread safety

        # def transmit_thread():
        #     #Takes the transmit window and transmits every packet that is allowed to be transmitted
        #     nonlocal base, next_seq, timeout_status, acked
        #     while base < packet_num:
        #         with lock:
        #             while next_seq < base + WINDOW_SIZE and next_seq < packet_num:
        #                 if timeout_status[next_seq] == 0:
        #                     packet = transmit_file[next_seq]
        #                     packet_index = next_seq.to_bytes(IDX_LENGTH, 'big')
        #                     tx_socket.sendto(packet_index + packet, addr)
        #                     timeout_status[next_seq] = time.time()  # record the time of sending
        #                     print(f"[DEBUG] Sent packet {next_seq+1}/{packet_num}")
        #                 next_seq += 1

        #             # check for timeouts and resend packets if necessary
        #             for i in range(base, min(base + WINDOW_SIZE, packet_num)):
        #                 if not acked[i] and timeout_status[i] > 0 and time.time() - timeout_status[i] > TIMEOUT:
        #                     # resend the packet if it has timed out
        #                     packet = transmit_file[i]
        #                     packet_index = i.to_bytes(IDX_LENGTH, 'big')
        #                     tx_socket.sendto(packet_index + packet, addr)
        #                     timeout_status[i] = time.time()
        #                     print(f"[DEBUG] Resent packet {i+1}/{packet_num} due to timeout")

        #         time.sleep(0.1)  # sleep to avoid busy waiting

        # def ack_thread():
        #     #Receives acknowledgement and updates the transmit window with sendable packets
        #     nonlocal base, next_seq, timeout_status, acked
        #     while base < packet_num:
        #         try:
        #             ack_data, _ = tx_socket.recvfrom(BUFSIZE)
        #             ack_idx = int.from_bytes(ack_data[:IDX_LENGTH], 'big')
        #             with lock:
        #                 if not acked[ack_idx]:
        #                     acked[ack_idx] = True
        #                     timeout_status[ack_idx] = -1
        #                     print(f"[DEBUG] Received ACK for packet {ack_idx+1}")
        #                     if ack_idx == base:
        #                         # move the base forward if the ACK is for the base packet
        #                         while base < packet_num and acked[base]:
        #                             base += 1
        #                         next_seq = max(next_seq, base)
        #         except socket.timeout:
        #             continue

        # #Create TX and RX threads and start doing it
        # tx = threading.Thread(target=transmit_thread)
        # ack = threading.Thread(target=ack_thread)
        # tx.start()
        # ack.start()
        # tx.join()
        # ack.join()

        # # When done transmitting, close the threads.
        # print("[DEBUG] Transmission complete. Closing socket.")
        # tx_socket.close()


        # addr = self.find_file(file_name) # addr is a tuple (hostname, port)
        # if not addr:
        #     print(f"[DEBUG] No peer found for file: {file_name}")
        #     return

        # # establish a client socket for downloading file
        # self.cl_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        # self.cl_socket.settimeout(TIMEOUT)  # set timeout for the socket

        # # Initiate three-way handshake and use a connect flag
        # connect_flag = False
        # while not connect_flag:
        #     try:
        #         # handshake
        #         print("[DEBUG] Sending SYN")
        #         initial_message = json.dumps({"type": "SYN", "file_name": file_name}).encode()
        #         self.cl_socket.sendto(initial_message, addr)
        #         data, _ = self.cl_socket.recvfrom(BUFSIZE)
        #         response = json.loads(data.decode())

        #         if response.get("type") == "SYN-ACK":
        #             connect_flag = True
        #             print("[DEBUG] Received SYN-ACK, sending ACK")
        #             # send ACK
        #             ack_message = json.dumps({"type": "ACK"}).encode()
        #             self.cl_socket.sendto(ack_message, addr)
        #     except socket.timeout:
        #         # handshake failed
        #         print("[DEBUG] Handshake timeout, retrying SYN")
        #         continue

        # # the receiver keeps a record for which part has been acked
        # try:
        #     pkt_count_data, _ = self.cl_socket.recvfrom(BUFSIZE)
        #     packet_num = int(pkt_count_data.decode())
        #     print(f"[DEBUG] Expecting {packet_num} packets for file {file_name}")
        # except socket.timeout:
        #     print("Failed to receive packet count, transmission aborted.")
        #     return

        # # start receiving file
        # received = [None] * packet_num  # to keep track of received packets
        # received_flags = [False] * packet_num  # to keep track of which packets have been acknowledged
        # total_received = 0  # total number of packets received

        # while total_received < packet_num:
        #     try:
        #         packet_data, _ = self.cl_socket.recvfrom(BUFSIZE)
        #         packet_index = int.from_bytes(packet_data[:IDX_LENGTH], 'big')
        #         packet_content = packet_data[IDX_LENGTH:]

        #         if not received_flags[packet_index]:
        #             received[packet_index] = packet_content
        #             received_flags[packet_index] = True
        #             total_received += 1
        #             print(f"[DEBUG] Received packet {packet_index+1}/{packet_num}")

        #             # send ACK for the received packet
        #             ack_message = packet_index.to_bytes(IDX_LENGTH, 'big')
        #             self.cl_socket.sendto(ack_message, addr)

        #     except socket.timeout:
        #         continue

        # # transmission complete, close socket
        # print("[DEBUG] All packets received. Closing client socket.")
        # self.cl_socket.close()

        # # write the file
        # try:
        #     with open(file_name, 'wb') as f:
        #         for packet in received:
        #             if packet is not None:
        #                 f.write(packet)
        #     print("File", file_name, "received successfully.")
        # except Exception as e:
        #     print("Error writing file:", e)