import socket
import threading
import unittest
from fd_adapter import TcpOverIpv4OverTunAdapter
from tcp_segment import *
from utils import uint32_plus


class TestTunAdapter(unittest.TestCase):
    def test_tcp_over_ip_over_tun(self):
        def tcp_server():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('192.168.3.137', 65431))
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

        t = threading.Thread(target=tcp_server)
        t.start()
        adapter = TcpOverIpv4OverTunAdapter('tun0')
        adapter.config.saddr = '192.0.2.2'
        adapter.config.sport = 30732
        adapter.config.daddr = '192.168.3.137'
        adapter.config.dport = 65431
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


if __name__ == '__main__':
    unittest.main()
