import unittest
from tcp_segment import *
from ipv4 import *


class TestSegment(unittest.TestCase):
    def test_same_segment(self):
        header = TcpHeader(
            sport=12345,
            dport=80,
            seqno=1000,
            ackno=2000,
            urg=True,
            ack=True,
            psh=True,
            win=8192,
            uptr=0
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

    def test_checksum(self):
        seg = TcpSegment(
            TcpHeader(
                syn=True,
                sport=30732,
                dport=80,
                seqno=4101019787
            ),
            b'',
            src_ip = '192.0.2.2',
            dst_ip = '34.194.149.67'
        )
        seg.serialize()
        self.assertEqual(seg.header.cksum, 0x3082)


class TestIPv4(unittest.TestCase):
    def test_same_datagram(self):
        header = IPv4Header(
            ver = 4,
            ihl = 5,
            tos = 0,
            length = 0,
            id = 0,
            df = True,
            mf = False,
            offset = 0,
            ttl = 64,
            proto = 6,
            src_ip = "192.168.1.1",
            dst_ip = "192.168.1.2",
        )
        dgram = IPv4Datagram(
            header,
            b'123456'
        )
        serialized_data = dgram.serialize()
        dgram2 = IPv4Datagram.deserialize(serialized_data)
        self.assertIsNotNone(dgram2)
        assert dgram2
        header2 = dgram2.header
        for f, v in header.__dict__.items():
            self.assertEqual(v, header2.__dict__[f])


if __name__ == '__main__':
    unittest.main()
