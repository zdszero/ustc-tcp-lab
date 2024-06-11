import unittest
from tcp_segment import *

class TestSegment(unittest.TestCase):
    def test_same_segment(self):
        header = TcpHeader(
            sport = 12345,
            dport = 80,
            seqno = 1000,
            ackno = 2000,
            urg = True,
            ack = True,
            psh = True,
            win = 8192,
            uptr = 0
        )

        src_ip = '192.168.1.1'
        dst_ip = '192.168.1.2'
        for payload in [b'this is some data', b'']:
            seg = TcpSegment(header, payload, src_ip, dst_ip)
            serialized_seg = seg.serialize()
            seg2 = TcpSegment.deserialize(serialized_seg, src_ip, dst_ip)
            self.assertIsNotNone(seg2)
            assert seg2
            for f, v in header.__dict__.items():
                self.assertEqual(v, seg2.header.__dict__[f])
            self.assertEqual(seg.payload, seg2.payload)


if __name__ == '__main__':
    unittest.main()
