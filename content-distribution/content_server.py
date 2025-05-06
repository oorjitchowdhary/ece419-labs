import argparse
import sys
import json
import socket
import threading
import time


class ContentServer:
    def __init__(self, config_file):
        self.config_file = config_file
        self.uuid = None
        self.name = None
        self.backend_port = None
        self.peer_count = None
        self.neighbors = {}

        self._load_config()

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
                self.peer_count = peer_count
                for _ in range(peer_count):
                    line = f.readline().strip()
                    peer_data = line.split('=')[1].strip().split(',')
                    uuid, hostname, backend_port, distance_metric = peer_data
                    self.neighbors[uuid] = {
                        'hostname': hostname,
                        'backend_port': int(backend_port),
                        'distance_metric': int(distance_metric)
                    }

        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    def print_uuid(self):
        print({'uuid': self.uuid})


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
                args = command.split()[1:]
                if len(args) != 4:
                    print("Usage: addneighbor <uuid> <host> <backend_port> <metric>")
                else:
                    server.add_neighbor(args)

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
