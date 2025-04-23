# Project 1: WiFi Receiver
## Design Document
--- Oorjit Chowdhary (oorjitc@uw.edu), EE 419/565 - Spring 2025

### Decoder Design

The `WiFiReceiver` function decodes the incoming signal from the `WiFiTransmitter` function, progressively reversing the encoding steps performed at each level. The decoding process is highlighted below:

**Level 1: Deinterleaving**

- The input is a stream of interleaved bits and the encoded length.
- The first $2 \cdot \text{nfft}$ bits represent the encoded message's length, which is figured out first by majority voting for each 3 bit group to determine the 42-43 bit length.
- The next $2 \cdot \text{nfft}$ bits are the interleaved message bits, which are deinterleaved using the pre-defined deinterleaving pattern that reverses the permutation applied at the transmitter.
- The deinterleaved bits are then converted to ASCII characters to return the plaintext message.

**Level 2: Demodulation & Viterbi Decode**

- The input is a 4-QAM modulated signal with encoded bits (that are interleaved) and a preamble.
- The input is first demodulated using the hard decision method, which maps the received signal to the nearest constellation point, and is then stripped of the preamble if the transmission level is below 4.
- After splitting the input into the length and message groups, the message bits are passed into my version of the Viterbi decoder to decode the encoded message.
- The pair of the encoded length bits and the decoded message bits are then passed to Level 1 to continue the decoding process.

**Level 3: OFDM Demodulation**

- Here, the input is an inverse FFT signal with OFDM symbols, which are then demodulated using the FFT method to get the frequency domain signal.
- The frequency domain signal is then passed to Level 2 to continue the decoding process.

**Level 4: Noise Handling**

- The input is a noisy signal with potential zero padding at the beginning and end, which need to be removed to get the actual signal.
- The receiver uses the known preamble to detect the start of the signal, by modulating and inverse FFTing the preamble to match the transmitter's signal.
- The receiver then uses a sliding window approach to measure similarity using absolute differences between the received signal and the preamble to find the initial zero padding.
- The zero padding is removed, and the signal is passed to Level 3 to continue the decoding process.

### Inferring Packet Length

The first $2 \cdot \text{nfft}$ bits of the signal represent the encoded length of the packet, which can be inferred using majority voting in 3-bit groups. For every 3 consecutive bits, the decoded bit is 1 if it has 2+ 1s, and 0 otherwise. This is done so because the transmitter added redundancy by repeating each bit of the original length thrice to ensure that the receiver can accurately determine the length even in the presence of noise.

### Extra Capabilities
N/A.
