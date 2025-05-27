sudo iptables -I OUTPUT -p udp -m udp --sport 18741 -j NFQUEUE --queue-num 1
sudo iptables -I OUTPUT -p udp -m udp --sport 18742 -j NFQUEUE --queue-num 1
# iptables -I INPUT -p udp -m udp --dport 18742 -j NFQUEUE --queue-num 1
