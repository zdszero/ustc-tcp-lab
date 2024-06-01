import unittest
import random

from config import TcpConfig
from tcp_connection import TcpConnection
from tcp_segment import TcpHeader, TcpSegment
from tcp_state import TcpState
from utils import UINT32_MAX, uint32_plus
from test_receiver import TcpTestBase


class SenderTestBase(TcpTestBase):
    def new_closed_connection(
        self,
        capacity: int,
        isn=random.randint(0, UINT32_MAX)
    ) -> TcpConnection:
        cfg = TcpConfig()
        cfg.send_capacity = capacity
        cfg.recv_capacity = capacity
        conn = TcpConnection(cfg, isn)
        return conn

    def new_eastablished_connection(
        self,
        capacity: int,
        isn=random.randint(0, UINT32_MAX),
        isn2=random.randint(0, UINT32_MAX)
    ) -> TcpConnection:
        cfg = TcpConfig()
        cfg.send_capacity = capacity
        cfg.recv_capacity = capacity
        conn = TcpConnection(cfg, isn)
        self.expectNoSegment(conn)
        conn.connect()
        self.assertEqual(conn.state, TcpState.SYN_SENT)
        self.expectSegment(conn, syn=True, seqno=isn)
        self.expectNoSegment(conn)
        conn.segment_received(TcpSegment(
            TcpHeader(syn=True, ack=True, ackno=uint32_plus(isn, 1), seqno=isn2)))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        self.expectSegment(conn, ack=True, ackno=uint32_plus(isn2, 1))
        self.expectNoSegment(conn)
        return conn


class SenderConnect(SenderTestBase):
    def test_three_handshake(self):
        isn = 10000
        isn2 = UINT32_MAX
        conn = self.new_closed_connection(4000, isn)
        conn.connect()
        self.assertEqual(conn.state, TcpState.SYN_SENT)
        self.expectSegment(conn, syn=True, seqno=isn)
        conn.segment_received(TcpSegment(
            TcpHeader(syn=True, ack=True, ackno=isn+1, seqno=isn2)))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        self.expectSegment(conn, ack=True, ackno=0)



class SenderWindow(SenderTestBase):
    def test_basic(self):
        cap = 1000
        isn, isn2 = 10000, 20000
        conn = self.new_eastablished_connection(cap, isn, isn2)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=isn+1, win=4)))
        self.expectNoSegment(conn)
        conn.write(b'1234567')
        self.expectSegment(conn, no_flags=True, payload=b'1234')

    def test_repeat(self):
        isn, isn2 = 10000, 20000
        min_win, max_win = 5, 100
        reps = 100
        for _ in range(reps):
            conn = self.new_eastablished_connection(4000, isn, isn2)
            recvwin = random.randint(min_win, max_win)
            conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=isn+1, win=recvwin)))
            self.expectNoSegment(conn)
            conn.write(b'a' * (2 * reps))
            self.expectSegment(conn, no_flags=True, payload_size=recvwin)
            self.expectNoSegment(conn)

    def test_window_growth(self):
        cap = 1000
        isn, isn2 = 10000, 20000
        conn = self.new_eastablished_connection(cap, isn, isn2)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=isn+1, win=4)))
        self.expectNoSegment(conn)
        conn.write(b'0123456789')
        self.expectSegment(conn, no_flags=True, payload=b'0123')
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=isn+5, win=5)))
        self.expectSegment(conn, no_flags=True, payload=b'45678')
        self.expectNoSegment(conn)

if __name__ == '__main__':
    unittest.main()
