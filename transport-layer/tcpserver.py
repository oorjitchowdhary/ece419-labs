import socket, sys
import json
import time
import threading
import uuid

# I ran into OSErrors on macOS with larger buffer sizes, so I reduced it
# BUFSIZE = 10202  # size of receiving buffer
# PKTSIZE = 10200  # number of bytes in a packet

IDX_LENGTH = 2 # 2 bytes of packet index
HEADER_SIZE = 1 + 16 + IDX_LENGTH  # 1 byte for packet type, 16 bytes for session ID, 2 bytes for packet index
PKTSIZE = 8190
BUFSIZE = PKTSIZE + HEADER_SIZE  # buffer size for receiving packets, including header
WINDOW_SIZE = 16
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
            "filename": file_name,
            "total_packets": 0,  # will be set after receiving SYN-ACK
            "received": [],  # to keep track of received packets
            "lock": threading.Lock(),  # lock for thread safety
            "complete": False,  # set to True when all packets are received
            "syn_ack_received": False,  # flag to check if SYN-ACK is received
            "syn_last_sent": 0,  # last time SYN was sent
        }

        # send SYN packet
        def syn_transmit():
            while not self.sessions[session_id]["syn_ack_received"]:
                now = time.time()
                if now - self.sessions[session_id]["syn_last_sent"] > TIMEOUT:
                    syn_packet = bytearray()
                    syn_packet.append(0x00)  # SYN packet type
                    syn_packet.extend(session_id)  # append session ID
                    syn_packet.append(len(filename_bytes))  # append length of filename
                    syn_packet.extend(filename_bytes)  # append filename
                    self.server_socket.sendto(syn_packet, addr)
                    self.sessions[session_id]["syn_last_sent"] = now  # update last sent time
                    print(f"[DEBUG] Sent SYN to {addr} for file '{file_name}' with session ID {session_id.hex()}")
                time.sleep(0.1)  # sleep to avoid busy waiting

        # start a thread to send SYN packets until SYN-ACK is received
        threading.Thread(target=syn_transmit).start()


    def transmit(self, file_name, addr, session_id):
        print(f"[DEBUG] Starting transmission to {addr} for file {file_name}")

        session = self.sessions[session_id]
        packets = self.read_file(file_name)  # read the file and get packets

        print(f"[DEBUG] Total packets to transmit: {len(packets)}")

        while session["base"] < session["total_packets"]:
            with session["lock"]:
                # send packets in the window
                while session["next_seq"] < session["base"] + WINDOW_SIZE and session["next_seq"] < session["total_packets"]:
                    if session["timeout_status"][session["next_seq"]] == 0:
                        data_packet = bytearray()
                        data_packet.append(0x03)  # Data packet type
                        data_packet.extend(session_id)  # append session ID

                        packet_index = session["next_seq"].to_bytes(IDX_LENGTH, 'big')
                        data_packet.extend(packet_index)  # append packet index
                        data_packet.extend(packets[session["next_seq"]])  # append packet data
                        self.server_socket.sendto(data_packet, addr)
                        session["timeout_status"][session["next_seq"]] = time.time()  # record the time of sending
                        print(f'[DEBUG] Sent packet {session["next_seq"] + 1}/{session["total_packets"]} to {addr}')

                    session["next_seq"] += 1

                # check for timeouts and resend packets if necessary
                for i in range(session["base"], min(session["base"] + WINDOW_SIZE, session["total_packets"])):
                    if not session["acked"][i] and session["timeout_status"][i] > 0 and time.time() - session["timeout_status"][i] > TIMEOUT:
                        # resend the packet if it has timed out
                        data_packet = bytearray()
                        data_packet.append(0x03)
                        data_packet.extend(session_id)  # append session ID

                        packet_index = i.to_bytes(IDX_LENGTH, 'big')
                        data_packet.extend(packet_index)  # append packet index
                        data_packet.extend(packets[i])  # append packet data
                        self.server_socket.sendto(data_packet, addr)
                        session["timeout_status"][i] = time.time()  # update the timeout status
                        print(f'[DEBUG] Resent packet {i + 1}/{session["total_packets"]} to {addr} due to timeout')

                while session["base"] < session["total_packets"] and session["acked"][session["base"]]:
                    # move the base forward if the ACK is for the base packet
                    session["base"] += 1
                    print(f'[DEBUG] Base moved to {session["base"]} for session ID {session_id.hex()}')

            time.sleep(0.1)  # sleep to avoid busy waiting


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
            "ready": False,  # set to True after ACK
            "ack_received": False,  # flag to check if ACK is received
            "syn_ack_last_sent": 0,  # last time SYN-ACK was sent
        }

        # send SYN-ACK response
        def syn_ack_transmit():
            while not self.sessions[session_id]["ack_received"]:
                now = time.time()
                if now - self.sessions[session_id]["syn_ack_last_sent"] > TIMEOUT:
                    syn_ack_packet = bytearray()
                    syn_ack_packet.append(0x01)
                    syn_ack_packet.extend(session_id)  # append session ID
                    syn_ack_packet.extend(total_packets.to_bytes(2, 'big'))  # append total packets count
                    self.server_socket.sendto(syn_ack_packet, addr)
                    self.sessions[session_id]["syn_ack_last_sent"] = now  # update last sent time
                    print(f"[DEBUG] Sent SYN-ACK to {addr} for session ID {session_id.hex()} with total packets {total_packets}")
                time.sleep(0.1)  # sleep to avoid busy waiting

        # start a thread to send SYN-ACK packets until ACK is received
        threading.Thread(target=syn_ack_transmit).start()


    def handle_syn_ack(self, packet, addr):
        session_id = packet[:16] # first 16 bytes are the session ID
        total_packets = int.from_bytes(packet[16:18], 'big')  # next 2 bytes are the total packets count

        print(f"[DEBUG] Received SYN-ACK from {addr} for session ID {session_id.hex()} with total packets {total_packets}")

        # update session entry (receiver side)
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session["total_packets"] = total_packets
            session["received"] = [None] * total_packets
            session["syn_ack_received"] = True  # mark SYN-ACK as received

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
        session["ack_received"] = True  # mark ACK as received

        # check if sender side and mark as ready
        if "ready" in session:
            with session["lock"]:
                session["ready"] = True
                print(f"[DEBUG] Session {session_id.hex()} is now ready for transmission.")

        threading.Thread(target=self.transmit, args=(session["filename"], addr, session_id)).start()
        print(f"[DEBUG] Transmission thread started for session ID {session_id.hex()}")


    def handle_data(self, packet, addr):
        session_id = packet[:16]
        packet_index = int.from_bytes(packet[16:18], 'big')  # next 2 bytes are the packet index
        packet_data = packet[18:]  # the rest is the packet data

        print(f"[DEBUG] Received DATA from {addr} for session ID {session_id.hex()} and packet index {packet_index}")

        if session_id not in self.sessions:
            print(f"[DEBUG] Session ID {session_id.hex()} not found in sessions.")
            return

        session = self.sessions[session_id]
        with session["lock"]:
            if packet_index < len(session["received"]):
                if not session["received"][packet_index]:
                    session["received"][packet_index] = packet_data
                    print(f"[DEBUG] Packet {packet_index} received for session ID {session_id.hex()}")

                    # check if all packets are received
                    if all(packet is not None for packet in session["received"]):
                        session["complete"] = True
                        print(f"[DEBUG] All packets received for session ID {session_id.hex()}. Transmission complete.")

                # send DATA-ACK back to the sender
                ack_packet = bytearray()
                ack_packet.append(0x04)
                ack_packet.extend(session_id)  # append session ID
                ack_packet.extend(packet_index.to_bytes(IDX_LENGTH, 'big'))  # append packet index
                self.server_socket.sendto(ack_packet, session["addr"])
                print(f"[DEBUG] Sent DATA-ACK for packet {packet_index} to {session['addr']} for session ID {session_id.hex()}")

        # if the session is complete, write the file
        if session["complete"]:
            print(f'[DEBUG] Writing received file {session["filename"]} for session ID {session_id.hex()}')
            try:
                with open(session["filename"], 'wb') as f:
                    for packet in session["received"]:
                        if packet is not None:
                            f.write(packet)
                print(f'[DEBUG] File {session["filename"]} written successfully.')
            except Exception as e:
                print(f'[DEBUG] Error writing file {session["filename"]}: {e}')

            # clean up the session
            del self.sessions[session_id]
            print(f"[DEBUG] Session {session_id.hex()} cleaned up.")


    def handle_data_ack(self, packet, addr):
        session_id = packet[:16]
        packet_index = int.from_bytes(packet[16:18], 'big')  # next 2 bytes are the packet index

        print(f"[DEBUG] Received DATA-ACK from {addr} for session ID {session_id.hex()} and packet index {packet_index}")

        if session_id not in self.sessions:
            print(f"[DEBUG] Session ID {session_id.hex()} not found in sessions.")
            return

        session = self.sessions[session_id]
        with session["lock"]:
            if not session["acked"][packet_index]:
                session["acked"][packet_index] = True
                session["timeout_status"][packet_index] = -1
                print(f"[DEBUG] Packet {packet_index} acknowledged for session ID {session_id.hex()}")

        if all(session["acked"]):
            # if all packets are acknowledged, mark the session as complete
            session["complete"] = True
            print(f"[DEBUG] All packets acknowledged for session ID {session_id.hex()}. Transmission complete.")

            # clean up the session
            del self.sessions[session_id]
            print(f"[DEBUG] Session {session_id.hex()} cleaned up.")


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
