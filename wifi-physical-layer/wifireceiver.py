# -*- coding: utf-8 -*-
from random import randint
import numpy as np
import sys
import commpy as comm
import commpy.channelcoding.convcode as check
from pip import main
import matplotlib.pyplot as plt


def WifiReceiver(input_stream, level):

    nfft = 64
    Interleave_tr = np.reshape(np.transpose(np.reshape(np.arange(1, 2*nfft+1, 1),[4,-1])),[-1,])
    Interleave_tr = np.reshape(np.transpose(np.reshape(np.arange(1, 2*nfft+1, 1),[-1,4])),[-1,])
    preamble = np.array([1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1,1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1])
    cc1 = check.Trellis(np.array([3]),np.array([[0o7,0o5]]))

    # set zero padding to be 0, by default
    begin_zero_padding = 0
    message = ""
    length = 0

    if level >= 4:
        #Input QAM modulated + Encoded Bits + OFDM Symbols in a long stream
        #Output Detected Packet set of symbols
        input_stream=input_stream

    if level >= 3:
        #Input QAM modulated + Encoded Bits + OFDM Symbols
        #Output QAM modulated + Encoded Bits
        input_stream=input_stream
    
    if level >= 2:
        #Input QAM modulated + Encoded Bits
        #Output Interleaved bits + Encoded Length
        input_stream=input_stream
       
    if level >= 1:
        #Input Interleaved bits + Encoded Length
        #Output Deinterleaved bits

        # first 128 bits of the stream represent the encoded length
        encoded_length = input_stream[:2*nfft]
        length_bin = ''
        for i in range(0, len(encoded_length), 3):
            # majority vote for each 3 bits
            bits = encoded_length[i:i+3]
            b = '0' if np.sum(bits) < 2 else '1'
            length_bin += b
        length = int(length_bin, 2)

        # remaining stream is message split in interleaved 2*nfft bit chunks
        chunks = input_stream[2*nfft:]
        deinterleave = np.zeros_like(Interleave_tr)
        deinterleave[Interleave_tr-1] = np.arange(2 * nfft)

        nsym = len(chunks) // (2 * nfft)
        deinterleaved = np.zeros_like(chunks, dtype=np.int8)
        for i in range(nsym):
            chunk = chunks[i * 2 * nfft:(i + 1) * 2 * nfft]
            deinterleaved[i * 2 * nfft:(i + 1) * 2 * nfft] = chunk[deinterleave]

        # remove any padding and convert bits to ASCII characters
        n_bits = length * 8
        bits = deinterleaved[:n_bits].astype(np.int8)
        message = ''.join([chr(b) for b in np.packbits(bits).tolist()])

        return begin_zero_padding, message, length

    raise Exception("Error: Unsupported level")


# for testing purpose
from wifitransmitter import WifiTransmitter
if __name__ == "__main__":
    np.set_printoptions(threshold=sys.maxsize)
    test_case = 'The Internet has transformed our everyday lives, bringing people closer together and powering multi-billion dollar industries. The mobile revolution has brought Internet connectivity to the last-mile, connecting billions of users worldwide. But how does the Internet work? What do oft repeated acronyms like "LTE", "TCP", "WWW" or a "HTTP" actually mean and how do they work? This course introduces fundamental concepts of computer networks that form the building blocks of the Internet. We trace the journey of messages sent over the Internet from bits in a computer or phone to packets and eventually signals over the air or wires. We describe commonalities and differences between traditional wired computer networks from wireless and mobile networks. Finally, we build up to exciting new trends in computer networks such as the Internet of Things, 5-G and software defined networking. Topics include: physical layer and coding (CDMA, OFDM, etc.); data link protocol; flow control, congestion control, routing; local area networks (Ethernet, Wi-Fi, etc.); transport layer; and introduction to cellular (LTE) and 5-G networks. The course will be graded based on quizzes (on canvas), a midterm and final exam and four projects (all individual). '
    print(test_case)
    output = WifiTransmitter(test_case, 1)
    print(output)
    begin_zero_padding, message, length_y = WifiReceiver(output, 1)
    print(begin_zero_padding, message, length_y)
    print(test_case == message)