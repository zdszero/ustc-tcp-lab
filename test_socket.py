import socket
import unittest
from fd_adapter import TcpOverIpv4OverTunAdapter
from tcp_segment import *


class TestTunAdapter(unittest.TestCase):
    def test_tcp_over_ip_over_tun(self):
        # sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # sock.bind(('127.0.0.1', 5678))
        # sock.listen()
        adapter = TcpOverIpv4OverTunAdapter('tun0')
        adapter.config.saddr = '192.0.2.2'
        adapter.config.sport = 30732
        adapter.config.daddr = '34.194.149.67'
        adapter.config.dport = 80
        adapter.listening = True
        adapter.write(TcpSegment(
            TcpHeader(
                syn=True,
                win=65535,
                seqno=4101019787
            )
        ))
        # seg = adapter.read()
        # print(seg)


if __name__ == '__main__':
    unittest.main()
