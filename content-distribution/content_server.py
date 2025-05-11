import argparse
import sys
import json
import socket
import threading
import time


class ContentServer:
    def __init__(self, config_file):
        self.config_file = config_file
        self.name, self.uuid, self.backend_port = None, None, None
        self.sock = None
        self.running = True
        self.neighbors = {}
        self.network_map = {}
        self.seq_seen = {} # highest seq seen for each neighbor

        self._load_config()
        self._setup_socket()

        threading.Thread(target=self.keepalive_loop, daemon=True).start()
        threading.Thread(target=self.receive_loop, daemon=True).start()
        threading.Thread(target=self.lsa_loop, daemon=True).start()

    def _load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                for _ in range(3):
                    line = f.readline().strip()
                    if line.startswith('uuid'):
                        self.uuid = line.split('=')[1].strip()
                    elif line.startswith('name'):
                        self.name = line.split('=')[1].strip()
                    elif line.startswith('backend_port'):
                        self.backend_port = int(line.split('=')[1].strip())

                peer_line = f.readline().strip()
                peer_count = int(peer_line.split('=')[1].strip())
                for _ in range(peer_count):
                    line = f.readline().strip()
                    peer_data = line.split('=')[1].strip().split(',')
                    uuid, hostname, backend_port, distance_metric = peer_data
                    self.neighbors[uuid] = {
                        'name': None, # will be found using LSA
                        'hostname': hostname,
                        'backend_port': int(backend_port),
                        'metric': int(distance_metric),
                        'is_alive': False, # will become True when we receive a keepalive
                        'last_seen': 0
                    }

        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    def _setup_socket(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(('', self.backend_port))
            print(f"Listening on {self.name}:{self.backend_port}")
        except Exception as e:
            print(f"Error setting up socket: {e}")
            sys.exit(1)

    def print_uuid(self):
        print({'uuid': self.uuid})

    def print_neighbors(self):
        live_neighbors = {}
        for uuid, data in self.neighbors.items():
            if data.get('is_alive', False):
                live_neighbors[data['name']] = {
                    'hostname': data['hostname'],
                    'backend_port': data['backend_port'],
                    'metric': data['distance_metric'],
                    'uuid': uuid
                }

        print({'neighbors': live_neighbors})

    def keepalive_loop(self):
        interval, timeout = 3, 10
        while self.running:
            now = time.time()
            for uuid, data in self.neighbors.items():
                self.send_keepalive(uuid)
                if data['is_alive'] and (now - data['last_seen'] > timeout):
                    print(f"Neighbor {uuid} is dead")
                    data['is_alive'] = False
                    self.send_lsa()
            time.sleep(interval)

    def send_keepalive(self, uuid):
        if uuid not in self.neighbors:
            print(f"Neighbor {uuid} not found")
            return

        message = {'type': 'keepalive', 'uuid': self.uuid}
        try:
            self.sock.sendto(json.dumps(message).encode(), (self.neighbors[uuid]['hostname'], self.neighbors[uuid]['backend_port']))
            print(f"Sent keepalive to {uuid}")
        except Exception as e:
            print(f"Error sending keepalive to {uuid}: {e}")

    def receive_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                message = json.loads(data.decode())
                self._handle_message(message, addr)
            except Exception as e:
                print(f"Error receiving message: {e}")
                continue
            time.sleep(0.1)

    def _handle_message(self, message, addr):
        if message['type'] == 'keepalive':
            uuid = message['uuid']
            if uuid in self.neighbors:
                self.neighbors[uuid]['is_alive'] = True
                self.neighbors[uuid]['last_seen'] = time.time()

        elif message['type'] == 'lsa':
            # Handle LSA messages here
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to the configuration file')
    args = parser.parse_args()

    server = ContentServer(args.c)

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            command = line.strip()

            if command == 'uuid':
                server.print_uuid()

            elif command == 'neighbors':
                server.print_neighbors()

            elif command.startswith('addneighbor'):
                _, uuid, hostname, backend_port, distance_metric = command.split()
                server.add_neighbor(uuid, hostname, int(backend_port), int(distance_metric))

            elif command == 'map':
                server.print_map()

            elif command == 'rank':
                server.print_rank()

            elif command == 'kill':
                server.kill()

            else:
                print(f"Unknown command: {command}")

        except Exception as e:
            print(f"Error in main loop: {e}")

if __name__ == "__main__":
    main()
