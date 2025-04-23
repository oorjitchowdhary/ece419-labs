# -*- coding: utf-8 -*-
from random import randint
import numpy as np
import sys
import commpy as comm
import commpy.channelcoding.convcode as check
from pip import main
import matplotlib.pyplot as plt


def find_start_index(signal, preamble):
    best_index = 0
    max_matches = np.inf

    # sliding window to find the best match for the preamble
    for i in range(len(signal) - len(preamble)):
        window = signal[i:i + len(preamble)]
        matches = np.sum(np.abs(window - preamble)) # count bits in window exactly equal to preamble
        if matches < max_matches:
            max_matches = matches
            best_index = i

    return best_index


def my_hard_vdecoder(bits, trellis):
    num_states = trellis.number_states
    k, n = trellis.k, trellis.n
    num_steps = len(bits) // n

    # initialize metrics and traceback
    path_metrics = np.full((num_states,), np.inf)
    path_metrics[0] = 0
    traceback = np.zeros((num_steps, num_states), dtype=int)

    # forward pass to compute path metrics over time in the trellis
    for t in range(num_steps):
        new_metrics = np.full((num_states,), np.inf)
        received = bits[t * n:(t + 1) * n]

        for prev_state in range(num_states):
            for input_bit in range(2 ** k):  # 0 or 1 if k=1
                next_state = trellis.next_state_table[prev_state, input_bit]
                expected = np.array(list(np.binary_repr(trellis.output_table[prev_state, input_bit], width=n)), dtype=int)
                metric = np.sum(received != expected)  # Hamming distance

                candidate_metric = path_metrics[prev_state] + metric
                if candidate_metric < new_metrics[next_state]:
                    new_metrics[next_state] = candidate_metric
                    traceback[t, next_state] = prev_state

        path_metrics = new_metrics

    # backtrack to find the best path
    states = np.zeros(num_steps, dtype=int)
    states[-1] = np.argmin(path_metrics)
    for t in range(num_steps - 1, 0, -1):
        states[t - 1] = traceback[t, states[t]]

    # recover input bits causing the state transitions
    decoded_bits = []
    for t in range(num_steps):
        prev = states[t - 1] if t > 0 else 0
        for input_bit in range(2 ** k):
            if trellis.next_state_table[prev, input_bit] == states[t]:
                decoded_bits.append(input_bit)
                break

    return np.array(decoded_bits, dtype=int)


def WifiReceiver(input_stream, level):
    nfft = 64
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

        # # unpack to find zero padding and message length if provided
        # if isinstance(input_stream, tuple) and len(input_stream) == 3:
        #     begin_zero_padding, input_stream, length = input_stream

        # # find zero padding through preamble indexing
        # else:
        print("input stream length", len(input_stream))

        # make preamble into signal-like array
        mod = comm.modulation.QAMModem(4)
        preamble = mod.modulate(preamble.astype(bool))

        nsym = int(len(preamble)/nfft)
        for i in range(nsym):
            symbol = preamble[i*nfft:(i+1)*nfft]
            preamble[i*nfft:(i+1)*nfft] = np.fft.ifft(symbol)

        begin_zero_padding = find_start_index(input_stream, preamble)
        print("begin_zero_padding length", begin_zero_padding)

        # remove initial padding
        input_stream = input_stream[begin_zero_padding:]
        input_stream = input_stream[len(preamble):]
        print("input stream length with zero padding and preamble removed", len(input_stream))

    if level >= 3:
        #Input QAM modulated + Encoded Bits + OFDM Symbols
        #Output QAM modulated + Encoded Bits

        # use FFT to switch to frequency domain
        nsym = int(len(input_stream)/nfft)
        print("complex symbols count", nsym)
        for i in range(nsym):
            symbol = input_stream[i*nfft:(i+1)*nfft]
            input_stream[i*nfft:(i+1)*nfft] = np.fft.fft(symbol)

        print("input stream length after FFT", len(input_stream))

    if level >= 2:
        #Input QAM modulated + Encoded Bits
        #Output Interleaved bits + Encoded Length

        # demodulate the stream
        mod = comm.modulation.QAMModem(4)
        demod = mod.demodulate(input_stream, demod_type='hard')

        print("input stream length after demodulation", len(demod))

        if level <= 3:
            # remove the preamble from the stream
            demod = demod[len(preamble):]

        # split into encoded length and message
        encoded_length = demod[:2*nfft]
        message = demod[2*nfft:]
        print("message length", len(message))

        # viterbi decode to get interleaved bits (which are handled by level 1)
        decoded_bits = my_hard_vdecoder(message, cc1)

        # prepare input for level 1 handling
        input_stream = np.concatenate((encoded_length, decoded_bits))

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

        # deinterleave the stream
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
    test_case = 'The Internet has transformed our everyday lives, bringing people closer together and powering multi-billion dollar industries. The mobile revolution has brought Internet connectivity to the last-mile, connecting billions of users worldwide. But how does the Internet work? What do oft repeated acronyms like "LTE", "TCP", "WWW" or a "HTTP" actually mean and how do they work? This course introduces fundamental concepts of computer networks that form the building blocks of the Internet. We trace the journey of messages sent over the Internet from bits in a computer or phone to packets and eventually signals over the air or wires. We describe commonalities and differences between traditional wired computer networks from wireless and mobile networks. Finally, we build up to exciting new trends in computer networks such as the Internet of Things, 5-G and software defined networking. Topics include: physical layer and coding (CDMA, OFDM, etc.); data link protocol; flow control, congestion control, routing; local area networks (Ethernet, Wi-Fi, etc.); transport layer; and introduction to cellular (LTE) and 5-G networks. The course will be graded based on quizzes (on canvas), a midterm and final exam and four projects (all individual). '
    print(test_case)
    output = WifiTransmitter(test_case, 2)
    begin_zero_padding, message, length_y = WifiReceiver(output, 2)
    print(begin_zero_padding, message, length_y)
    print(test_case == message)
