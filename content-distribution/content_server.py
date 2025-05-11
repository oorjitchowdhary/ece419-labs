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
                        'hostname': hostname.strip(),
                        'backend_port': int(backend_port.strip()),
                        'metric': int(distance_metric.strip()),
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
                    'metric': data['metric'],
                    'uuid': uuid
                }

        print({'neighbors': live_neighbors})

    def add_neighbor(self, uuid, hostname, backend_port, distance_metric):
        if uuid in self.neighbors:
            print(f"Neighbor {uuid} already exists")
            return

        self.neighbors[uuid] = {
            'name': None,
            'hostname': hostname,
            'backend_port': backend_port,
            'metric': distance_metric,
            'is_alive': True,
            'last_seen': time.time()
        }
        self.send_keepalive(uuid)
        self.emit_lsa()

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
            # print(f"Sent keepalive to {uuid}")
        except Exception as e:
            print(f"Error sending keepalive to {uuid}: {e}")

    def receive_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
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
            else:
                print(f"Received keepalive from unknown neighbor {uuid}")
                self.neighbors[uuid] = {
                    'name': None,
                    'hostname': addr[0],
                    'backend_port': addr[1],
                    'metric': 0,
                    'is_alive': True,
                    'last_seen': time.time()
                }
                self.emit_lsa()

        elif message['type'] == 'lsa':
            uuid, seq = message['uuid'], message['seq']
            if uuid not in self.neighbors:
                print(f"Received LSA from unknown neighbor {uuid}")
                return
            if seq < self.seq_seen.get(uuid, 0):
                print(f"Received outdated LSA from {uuid}")
                return

            self.seq_seen[uuid] = seq
            self.neighbors[uuid]['name'] = message['name']

            self.network_map[message['name']] = {}
            for neighbor_uuid, metric in message['neighbors'].items():
                if neighbor_uuid != self.uuid:
                    neighbor_name = self.neighbors[neighbor_uuid]['name']
                    self.network_map[message['name']][neighbor_name] = metric

            self.broadcast(message, exclude=uuid)

    def lsa_loop(self):
        interval = 5
        seq = 0
        while self.running:
            seq += 1
            self.emit_lsa(seq)
            time.sleep(interval)

    def emit_lsa(self, seq=None):
        if seq is None:
            seq = self.seq_seen.get(self.uuid, 0) + 1
        self.seq_seen[self.uuid] = seq

        lsa = {
            'type': 'lsa',
            'uuid': self.uuid,
            'seq': seq,
            'name': self.name,
            'neighbors': {u: data['metric'] for u, data in self.neighbors.items() if data['is_alive']},
        }

        self.broadcast(lsa)

    def broadcast(self, message, exclude=None):
        for uuid, data in self.neighbors.items():
            if uuid == exclude:
                continue
            try:
                self.sock.sendto(json.dumps(message).encode(), (data['hostname'], data['backend_port']))
                # print(f"Broadcasted message to {uuid}")
            except Exception as e:
                print(f"Error broadcasting to {uuid}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to the configuration file')
    args = parser.parse_args()

    server = ContentServer(args.config)

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
                _, uuid_arg, hostname_arg, backend_port_arg, distance_metric_arg = command.split()
                uuid = uuid_arg.split('=')[1]
                hostname = hostname_arg.split('=')[1]
                backend_port = backend_port_arg.split('=')[1]
                distance_metric = distance_metric_arg.split('=')[1]
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
