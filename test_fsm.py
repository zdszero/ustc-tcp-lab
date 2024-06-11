import unittest
import os
import select
import random
from math import ceil
from typing import Optional

from config import TcpConfig
from tcp_connection import TcpConnection
from tcp_segment import TcpHeader, TcpSegment
from utils import UINT32_MAX
from test_sender import SenderTestBase

class FsmTestBase(SenderTestBase):
    def setUp(self):
        self.r_fd, self.w_fd = os.pipe()
        self.conn = None

    def canRead(self) -> bool:
        readable, _, _ = select.select([self.r_fd], [], [], 0)
        return len(readable) > 0

    def writeSegments(self, conn: TcpConnection):
        for seg in conn.segments_out:
            os.write(self.w_fd, seg.serialize())
        conn.segments_out.clear()

    def readNoSegment(
        self
    ):
        self.assertTrue(not self.canRead())

    def readSegment(
        self,
        payload_size: int,
        no_flags: bool = False,
        syn: Optional[bool] = None,
        ack: Optional[bool] = None,
        fin: Optional[bool] = None,
        seqno: Optional[int] = None,
        ackno: Optional[int] = None,
        win: Optional[int] = None,
        payload: Optional[bytes] = None
    ) -> TcpSegment:
        self.assertTrue(self.canRead())
        data = os.read(self.r_fd, payload_size + TcpHeader.LENGTH)
        seg = TcpSegment.deserialize(data)
        assert seg
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
        return seg


class FsmTest(FsmTestBase):
    def test_loopback(self):
        capacity = 65000
        for _ in range(64):
            offset = random.randint(capacity, UINT32_MAX)
            conn = self.new_eastablished_connection(65000, offset-1, offset-1)
            conn.segment_received(TcpSegment(
                TcpHeader(ack=True, seqno=offset, ackno=offset, win=capacity)))
            data = random.randbytes(capacity)
            recv_data = b''

            sendoff = 0
            while sendoff < capacity:
                len = min(capacity - sendoff, random.randint(0, 8191))
                if len == 0:
                    continue
                conn.write(data[sendoff:sendoff+len])
                conn.tick(1)
                self.writeSegments(conn)
                self.assertEqual(conn.bytes_in_flight, len)
                self.assertTrue(self.canRead())
                
                n_segents = ceil(len / TcpConfig.MAX_PAYLOAD_SIZE)
                bytes_remaining = len

                # transfer the data segment
                for _ in range(n_segents):
                    expected_size = min(bytes_remaining, TcpConfig.MAX_PAYLOAD_SIZE)
                    seg = self.readSegment(payload_size=expected_size)
                    self.assertIsNotNone(seg)
                    assert seg
                    bytes_remaining -= expected_size
                    conn.segment_received(seg)
                    conn.tick(1)
                    recv_data += seg.payload

                self.writeSegments(conn)

                # transfer the bare ack segment
                for _ in range(n_segents):
                    seg = self.readSegment(payload_size=0, ack=True)
                    self.assertIsNotNone(seg)
                    assert seg
                    conn.segment_received(seg)
                    conn.tick(1)

                self.writeSegments(conn)
                self.readNoSegment()
                self.assertEqual(conn.bytes_in_flight, 0)

                sendoff += len

            self.assertEqual(data, recv_data)


if __name__ == '__main__':
    unittest.main()
