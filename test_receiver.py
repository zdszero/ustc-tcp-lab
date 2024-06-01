import random
import unittest
from typing import Optional

from tcp_segment import TcpSegment, TcpHeader
from tcp_connection import TcpConnection
from tcp_state import TcpState
from config import TcpConfig
from utils import UINT32_MAX, uint32_plus


class TcpTestBase(unittest.TestCase):
    def expectBytes(self, conn: TcpConnection, expected: bytes):
        size = conn.outbound_stream.size
        self.assertEqual(conn.outbound_stream.read(size), expected)

    def expectNoSegment(
        self,
        conn: TcpConnection
    ):
        self.assertEqual(len(conn.segments_out), 0)

    def expectSegment(
        self,
        conn: TcpConnection,
        no_flags: bool = False,
        syn: Optional[bool] = None,
        ack: Optional[bool] = None,
        fin: Optional[bool] = None,
        seqno: Optional[int] = None,
        ackno: Optional[int] = None,
        win: Optional[int] = None,
        payload_size: Optional[int] = None,
        payload: Optional[bytes] = None
    ):
        self.assertGreater(len(conn.segments_out), 0)
        seg = conn.segments_out.popleft()
        if no_flags:
            self.assertEqual(seg.header.syn, False)
            self.assertEqual(seg.header.ack, False)
            self.assertEqual(seg.header.fin, False)
            self.assertEqual(seg.header.urg, False)
        if syn is not None:
            self.assertEqual(seg.header.syn, syn)
        if ack is not None:
            self.assertEqual(seg.header.ack, ack)
        if fin is not None:
            self.assertEqual(seg.header.fin, fin)
        if seqno is not None:
            self.assertEqual(seg.header.seqno, seqno)
        if ackno is not None:
            self.assertEqual(seg.header.ackno, ackno)
        if win is not None:
            self.assertEqual(seg.header.win, win)
        if payload_size is not None:
            self.assertEqual(len(seg.payload), payload_size)
        if payload is not None:
            self.assertEqual(seg.payload, payload)


class ReceiverTestBase(TcpTestBase):
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
        self, capacity: int,
        isn: int = random.randint(0, UINT32_MAX)
    ) -> TcpConnection:
        cfg = TcpConfig()
        cfg.send_capacity = capacity
        cfg.recv_capacity = capacity
        conn = TcpConnection(cfg, sender_isn=isn)
        conn.set_listening()
        conn.segment_received(TcpSegment(TcpHeader(syn=True, seqno=isn)))
        self.assertEqual(conn.state, TcpState.SYN_RECEIVED)
        self.expectSegment(conn, syn=True, seqno=isn, ack=True, ackno=uint32_plus(isn, 1))
        conn.segment_received(TcpSegment(
            TcpHeader(syn=True, ack=True, seqno=uint32_plus(isn, 1), ackno=uint32_plus(isn, 1))))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        return conn


class TestReceiverConnect(ReceiverTestBase):

    def three_way_handshake(self):
        sender_isn, receiver_isn = 10000, 20000
        conn = self.new_closed_connection(4000)
        conn.set_listening()
        self.assertEqual(conn.state, TcpState.LISTEN)
        # first handshake
        conn.segment_received(TcpSegment(TcpHeader(syn=True, seqno=receiver_isn)))
        # second handshake
        self.expectSegment(conn, syn=True, ack=True, seqno=sender_isn, ackno=receiver_isn+1)
        self.assertEqual(conn.state, TcpState.SYN_RECEIVED)
        self.assertEqual(conn.assembled_bytes, 0)
        self.assertEqual(conn.unassembled_bytes, 0)
        # wrong third handshake
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn-1)))
        self.assertEqual(conn.state, TcpState.SYN_RECEIVED)
        # third handshake
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+1)))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)


class TestReceiverRecord(ReceiverTestBase):
    def test_later_segment(self):
        """
        An in window, but later segment
        """
        isn = random.randint(0, UINT32_MAX)
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 10)), b'1234'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.unassembled_bytes, 4)
        self.assertEqual(conn.assembled_bytes, 0)

    def test_hole_filled(self):
        """
        An in window, but later segment, then the hole is filled
        """
        isn = random.randint(0, UINT32_MAX)
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 5)), b'efgh'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.unassembled_bytes, 4)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 1)), b'abcd'))
        self.expectBytes(conn, b'abcdefgh')
        self.assertEqual(conn.ackno, uint32_plus(isn, 9))
        self.assertEqual(conn.unassembled_bytes, 0)
        self.assertEqual(conn.assembled_bytes, 8)

    def test_hole_filled_gradually(self):
        """
        An in-window, but later segment, then the hole is filled, bit by bit
        """
        isn = random.randint(0, UINT32_MAX)
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 5)), b'efgh'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.unassembled_bytes, 4)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 1)), b'ab'))
        self.assertEqual(conn.ackno, uint32_plus(isn, 3))
        self.expectBytes(conn, b'ab')
        self.assertEqual(conn.unassembled_bytes, 4)
        self.assertEqual(conn.assembled_bytes, 2)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 3)), b'cd'))
        self.assertEqual(conn.ackno, uint32_plus(isn, 9))
        self.assertEqual(conn.unassembled_bytes, 0)
        self.assertEqual(conn.assembled_bytes, 8)

    def test_many_gaps(self):
        """
        Many gaps, then filled bit by bit.
        """
        isn = random.randint(0, UINT32_MAX)
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 5)), b'e'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 1)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 7)), b'g'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 2)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 3)), b'c'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 3)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 1)), b'ab'))
        self.expectBytes(conn, b'abc')
        self.assertEqual(conn.ackno, uint32_plus(isn, 4))
        self.assertEqual(conn.unassembled_bytes, 2)
        self.assertEqual(conn.assembled_bytes, 3)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 6)), b'f'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 4))
        self.assertEqual(conn.unassembled_bytes, 3)
        self.assertEqual(conn.assembled_bytes, 3)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 4)), b'd'))
        self.expectBytes(conn, b'defg')
        self.assertEqual(conn.ackno, uint32_plus(isn, 8))
        self.assertEqual(conn.unassembled_bytes, 0)
        self.assertEqual(conn.assembled_bytes, 7)

    def test_gaps_subsumed(self):
        """
        Many gaps, then subsumed
        """
        isn = random.randint(0, UINT32_MAX)
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 5)), b'e'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 1)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 7)), b'g'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 2)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 3)), b'c'))
        self.expectBytes(conn, b'')
        self.assertEqual(conn.ackno, uint32_plus(isn, 1))
        self.assertEqual(conn.unassembled_bytes, 3)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=uint32_plus(isn, 1)), b'abcdefgh'))
        self.expectBytes(conn, b'abcdefgh')
        self.assertEqual(conn.ackno, uint32_plus(isn, 9))
        self.assertEqual(conn.unassembled_bytes, 0)
        self.assertEqual(conn.assembled_bytes, 8)


class TestReceiverClose(ReceiverTestBase):
    def test_last_ack(self):
        isn = 10000
        conn = self.new_eastablished_connection(4000, isn)
        conn.segment_received(TcpSegment(
            TcpHeader(fin=True, seqno=isn+1),
            payload=b'12')
        )
        conn.inbound_stream.end_input()
        conn.segment_received(TcpSegment(TcpHeader(fin=True)))
        self.assertEqual(conn.state, TcpState.LAST_ACK)

    def test_last_ack2(self):
        """
        At first there is some data not received before fin,
        then the data is received.
        """
        isn = 10000
        conn = self.new_eastablished_connection(4000, isn)
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=isn+3, fin=True), payload=b'3456'))
        self.assertEqual(conn.state, TcpState.CLOSE_WAIT)
        conn.inbound_stream.end_input()
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=isn+1), payload=b'12'))
        self.assertEqual(conn.state, TcpState.LAST_ACK)

    def test_closed(self):
        """
        At first there is some data not received before fin,
        then the data is received.
        """
        isn = 10000
        conn = self.new_eastablished_connection(4000, isn)
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=isn+3, fin=True), payload=b'3456'))
        self.assertEqual(conn.state, TcpState.CLOSE_WAIT)
        conn.inbound_stream.end_input()
        conn.segment_received(TcpSegment(
            TcpHeader(seqno=isn+1), payload=b'12'))
        self.assertEqual(conn.state, TcpState.LAST_ACK)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=isn+2)))
        self.assertEqual(conn.state, TcpState.CLOSED)


class ReceiverWindowTest(ReceiverTestBase):
    def test_window_size(self):
        cap = 4000
        isn = 1000
        # window size decreases appropriately
        conn = self.new_eastablished_connection(cap, isn)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+1), b'abcd'))
        self.expectSegment(conn, ack=True, ackno=isn+5, win=cap-4)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+9), b'ijkl'))
        self.expectSegment(conn, ack=True, ackno=isn+5, win=cap-4)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+5), b'efgh'))
        self.expectSegment(conn, ack=True, ackno=isn+13, win=cap-12)
        # window size expands on read
        conn.outbound_stream.read(4)
        self.assertEqual(conn.window_size, cap-8)

    def test_window_size2(self):
        # almost-high-seqno segment is accepted, but only some bytes are kept
        cap = 2
        isn = 1000
        conn = self.new_eastablished_connection(cap, isn)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+2), b'bc'))
        self.expectSegment(conn, ackno=isn+1, win=2)
        self.assertEqual(conn.assembled_bytes, 0)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+1), b'a'))
        self.expectSegment(conn, ackno=isn+3, win=0)
        self.assertEqual(conn.assembled_bytes, 2)
        self.expectBytes(conn, b'ab')

    def test_window_size3(self):
        # almost-low-seqno segment is accepted
        cap = 4
        isn = 1000
        conn = self.new_eastablished_connection(cap, isn)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+1), b'ab'))
        self.assertEqual(conn.assembled_bytes, 2)
        self.assertEqual(conn.window_size, cap-2)
        conn.segment_received(TcpSegment(TcpHeader(seqno=isn+1), b'abc'))
        self.assertEqual(conn.assembled_bytes, 3)
        self.assertEqual(conn.window_size, cap-3)


if __name__ == '__main__':
    unittest.main()
