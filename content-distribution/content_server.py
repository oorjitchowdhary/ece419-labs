import argparse
import sys
import json
import socket
import threading
import time
import logging

class ContentServer:
    def __init__(self, config_file):
        self.config_file = config_file
        self.name, self.uuid, self.backend_port = None, None, None
        self.sock = None
        self.running = True
        self.neighbors = {}
        self.name_map = {}
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
                    uuid, host, backend_port, metric = peer_data
                    self.neighbors[uuid] = {
                        'host': host.strip(),
                        'backend_port': int(backend_port.strip()),
                        'metric': int(metric.strip()),
                        'is_alive': True, # assume alive at start
                        'last_seen': 0
                    }

            # add yourself to global network map
            self.network_map[self.uuid] = {
                uuid: data['metric'] for uuid, data in self.neighbors.items() if data['is_alive']
            }
            self.name_map[self.uuid] = self.name
            self.seq_seen[self.uuid] = 0

            # logging.info(f"Loaded config: {self.name}, {self.uuid}, {self.backend_port}")

        except Exception as e:
            # logging.error(f"Error loading config file: {e}")
            sys.exit(1)

    def _setup_socket(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(('', self.backend_port))
            # logging.info(f"Listening on port {self.backend_port}")
        except Exception as e:
            # logging.error(f"Error setting up socket: {e}")
            sys.exit(1)

    def print_uuid(self):
        print(json.dumps({'uuid': self.uuid}))

    def print_neighbors(self):
        alive_neighbors = {}
        for uuid, data in self.neighbors.items():
            if data.get('is_alive', False):
                alive_neighbors[self.name_map.get(uuid, uuid)] = {
                    'uuid': uuid,
                    'host': data['host'],
                    'backend_port': data['backend_port'],
                    'metric': data['metric']
                }

        print(json.dumps({'neighbors': alive_neighbors}))

    def add_neighbor(self, uuid, host, backend_port, metric):
        if uuid in self.neighbors:
            # logging.error(f"Neighbor {uuid} already exists")
            return

        self.neighbors[uuid] = {
            'name': None,
            'host': host,
            'backend_port': backend_port,
            'metric': metric,
            'is_alive': True,
            'last_seen': time.time()
        }
        self.send_keepalive(uuid)
        self.send_lsa()

    def keepalive_loop(self):
        interval, timeout = 3, 9
        while self.running:
            now = time.time()
            for uuid, data in self.neighbors.items():
                if data['is_alive']:
                    self.send_keepalive(uuid)

                    if now - data['last_seen'] > timeout:
                        # logging.warning(f"Neighbor {uuid} is not responding, marking as dead")
                        data['is_alive'] = False
                        self.send_lsa()

            time.sleep(interval)

    def lsa_loop(self):
        interval = 5
        seq = 0
        while self.running:
            seq += 1
            self.send_lsa(seq)
            time.sleep(interval)

    def receive_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = json.loads(data.decode())
                self._handle_message(message, addr)
            except Exception as e:
                # logging.error(f"Error receiving message: {e}")
                continue
            time.sleep(0.1)

    def _handle_message(self, message, addr):
        if message['type'] == 'keepalive':
            uuid = message['uuid']
            if uuid in self.neighbors:
                self.neighbors[uuid]['is_alive'] = True
                self.neighbors[uuid]['last_seen'] = time.time()

        elif message['type'] == 'lsa':
            origin_uuid = message['uuid']
            origin_seq = message['seq']
            origin_name = message['name']
            neighbor_info = message['neighbors']

            # ignore outdated LSAs
            if origin_seq <= self.seq_seen.get(origin_uuid, -1):
                # logging.info(f"Received outdated LSA from {origin_uuid} with seq {origin_seq}, ignoring")
                return

            # update seq number and global map states
            self.seq_seen[origin_uuid] = origin_seq
            self.name_map[origin_uuid] = origin_name
            self.network_map[origin_uuid] = neighbor_info

            # determine sender to not forward back
            sender_uuid = None
            for uuid, data in self.neighbors.items():
                if data['host'] == addr[0] and data['backend_port'] == addr[1]:
                    sender_uuid = uuid
                    break

            # broadcast the LSA to all neighbors
            self.broadcast(message, exclude=sender_uuid)

    def send_keepalive(self, uuid):
        if uuid not in self.neighbors:
            # logging.error(f"Neighbor {uuid} not found while sending keepalive")
            return

        message = {'type': 'keepalive', 'uuid': self.uuid, 'name': self.name}
        try:
            self.sock.sendto(json.dumps(message).encode(), (self.neighbors[uuid]['host'], self.neighbors[uuid]['backend_port']))
        except Exception as e:
            pass
            # logging.error(f"Error sending keepalive to {uuid}: {e}")

    def send_lsa(self, seq=None):
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
                self.sock.sendto(json.dumps(message).encode(), (data['host'], data['backend_port']))
                # logging.info(f"Broadcasted message to {uuid}")
            except Exception as e:
                pass
                # logging.error(f"Error broadcasting message to {uuid}: {e}")

    def dijkstra(self, start):
        path = {}
        nodes = set(self.network_map.keys())
        distances = {node: float('inf') for node in nodes}
        distances[start] = 0

        while nodes:
            min_node = None
            for node in nodes:
                if min_node is None or distances[node] < distances[min_node]:
                    min_node = node

            if distances[min_node] == float('inf'):
                break  # Remaining nodes are unreachable

            nodes.remove(min_node)

            for neighbor, weight in self.network_map.get(min_node, {}).items():
                alt = distances[min_node] + weight
                if alt < distances.get(neighbor, float('inf')):
                    distances[neighbor] = alt
                    path[neighbor] = min_node

        return distances, path

    def print_map(self):
        print({'map': self.network_map})

    def print_rank(self):
        distances, _ = self.dijkstra(self.uuid)
        ranked = {
            self.name_map.get(uuid, uuid): cost for uuid, cost in distances.items() if uuid != self.uuid
        }
        print(json.dumps({'rank': ranked}))

    def kill(self):
        self.running = False
        self.sock.close()
        sys.exit(0)


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
                while ' =' in command:
                    command = command.replace(' =', '=')
                while '= ' in command:
                    command = command.replace('= ', '=')

                tokens = command.split()
                args = {}
                for token in tokens[1:]:
                    key, value = token.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    args[key] = value

                uuid = args.get('uuid')
                host = args.get('host')
                backend_port = int(args.get('backend_port'))
                metric = int(args.get('metric'))
                server.add_neighbor(uuid, host, backend_port, metric)

            elif command == 'map':
                server.print_map()

            elif command == 'rank':
                server.print_rank()

            else:
                server.kill()

        except Exception as e:
            pass
            # logging.error(f"Error processing command: {e}")

if __name__ == "__main__":
    main()
