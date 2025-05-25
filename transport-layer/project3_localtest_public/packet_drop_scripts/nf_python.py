from netfilterqueue import NetfilterQueue
import sys
import random
import signal

def acceptAndControlledDrop(pkt):
    probability = float(sys.argv[1])
    if random.random() < probability:
    	pkt.drop()
    else:
    	pkt.accept()

def signal_handler(sig, frame):
    global nfqueue
    print('[nf_python] unbind successful')
    nfqueue.unbind()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)

nfqueue = NetfilterQueue()
nfqueue.bind(1, acceptAndControlledDrop)

try:
    nfqueue.run()
except KeyboardInterrupt:
    print('')

nfqueue.unbind()