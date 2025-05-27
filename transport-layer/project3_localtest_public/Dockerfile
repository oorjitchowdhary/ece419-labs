FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Basic tools and system updates
RUN apt update && apt install -y \
    python3 \
    python3-pip \
    python3-dev \
    iptables \
    libnfnetlink-dev \
    libnetfilter-queue-dev \
    sudo \
    net-tools

# Python library needed for packet filter
RUN pip3 install nfqp3

# Default working directory inside container
WORKDIR /workspace

CMD ["/bin/bash"]
