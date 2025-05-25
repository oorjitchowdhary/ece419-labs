sudo iptables -D OUTPUT -p udp -m udp --sport 18741 -j NFQUEUE --queue-num 1
sudo iptables -D OUTPUT -p udp -m udp --sport 18742 -j NFQUEUE --queue-num 1

# iptables -D INPUT -p udp -m udp --dport 18742 -j NFQUEUE --queue-num 1
