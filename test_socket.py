import socket
import os
import threading
import unittest
from config import FdAdapterConfig
from event_loop import *
from tcp_segment import *
from utils import *
from fd_adapter import TcpOverIpv4OverTunAdapter
from tcp_socket import TcpSocket


def tcp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('192.168.3.137', 65430))
    s.listen()
    print("Server is listening...")
    s.settimeout(2)  # Add timeout to prevent hanging forever
    try:
        conn, peer_addr = s.accept()
        print(f'Accepted connection from {peer_addr}')
        conn.close()
    except socket.timeout:
        print("Server timed out waiting for a connection.")
    finally:
        s.close()

        print("Server socket closed.")


testcfg = FdAdapterConfig(
    saddr='169.254.0.9',
    sport=30732,
    daddr='192.168.3.137',
    dport=65430
)


class TestTunAdapter(unittest.TestCase):
    def test_tcp_over_ip_over_tun(self):
        t = threading.Thread(target=tcp_server)
        t.start()
        adapter = TcpOverIpv4OverTunAdapter('tun0')
        adapter.config = testcfg
        adapter.listening = True

        # Write SYN segment
        adapter.write(TcpSegment(
            TcpHeader(
                syn=True,
                win=65535,
                seqno=10000
            )
        ))
        print("SYN segment written.")

        # Read SYN-ACK segment
        seg = adapter.read()
        self.assertIsNotNone(seg)
        assert seg
        self.assertTrue(seg.header.syn)
        self.assertTrue(seg.header.ack)
        self.assertEqual(seg.header.ackno, 10001)
        print("SYN-ACK segment received.")

        # Write ACK segment
        next_seqno = uint32_plus(seg.header.seqno, 1)
        adapter.write(TcpSegment(
            TcpHeader(
                ack=True,
                win=65535,
                ackno=next_seqno,
                seqno=10001
            )
        ))
        print("ACK segment written.")

        t.join()


class TestSocket(unittest.TestCase):
    def test_socket(self):
        t = threading.Thread(target=tcp_server)
        t.start()
        s = TcpSocket(TcpOverIpv4OverTunAdapter("tun0"))
        s.connect(testcfg)
        request = "GET / HTTP/1.1\r\nHost: {}\r\n\r\n".format('192.168.31.128')
        s.write(request)
        t.join()


# class TestEventloop(unittest.TestCase):
#     def test_basic(self):
#         loop = EventLoop()
#         r, w = socket.socketpair()
#         loop.add_rule(r, READ_EVENT, lambda: print('readable'))
#         loop.add_rule(w, WRITE_EVENT, lambda: print('writable'))
#         w.send(b'12345')
#         loop.wait_next_event(100)
#         r.close()
#         w.close()


if __name__ == '__main__':
    unittest.main()
