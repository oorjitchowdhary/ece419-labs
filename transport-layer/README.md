## Packet Format
0x00 - SYN - 16 bytes session ID, 1 byte filename length, remaining bytes are the filename
0x01 - SYN-ACK - 16 bytes session ID, 2 bytes packets count
0x02 - ACK - 16 bytes session ID

0x03 - DATA - 16 bytes session ID, 2 bytes packet number, remaining bytes are the data
0x04 - DATA-ACK - 16 bytes session ID, 2 bytes packet index

0x05 - FIN - 16 bytes session ID
0x06 - FIN-ACK - 16 bytes session ID
