import struct
from typing import Optional

from utils import checksum, inet_aton

"""
     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |          Source Port          |       Destination Port        |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                        Sequence Number                        |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                    Acknowledgment Number                      |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |  Data |           |U|A|P|R|S|F|                               |
    | Offset| Reserved  |R|C|S|S|Y|I|            Window             |
    |       |           |G|K|H|T|N|N|                               |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |           Checksum            |         Urgent Pointer        |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                    Options                    |    Padding    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                             data                              |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
"""

TCP_HEADER_LENGTH = 20
IPPROTO_TCP = 6


def tcp_checksum(src_ip: str, dst_ip: str, tcp_header: bytes, tcp_data: bytes):
    if not src_ip or not dst_ip:
        raise ValueError('source and destination ip address cannot be null in tcp_checksum')
    pseudo_header = struct.pack("!IIBBH",
                                inet_aton(src_ip),
                                inet_aton(dst_ip),
                                0,
                                IPPROTO_TCP,
                                len(tcp_header) + len(tcp_data))
    return checksum(pseudo_header + tcp_header + tcp_data)


class TcpHeader:
    def __init__(
        self,
        sport = 0,
        dport = 0,
        seqno = 0,
        ackno = 0,
        doff = TCP_HEADER_LENGTH // 4,
        urg = False,
        ack = False,
        psh = False,
        rst = False,
        syn = False,
        fin = False,
        win = 0,
        cksum = 0,
        uptr = 0
    ):
        self.sport = sport
        self.dport = dport
        self.seqno = seqno
        self.ackno = ackno
        self.doff = doff
        self.urg = urg
        self.ack = ack
        self.psh = psh
        self.rst = rst
        self.syn = syn
        self.fin = fin
        self.win = win
        self.cksum = cksum
        self.uptr = uptr

    def serialize(self, src_ip: str, dst_ip: str, payload_data: bytes):
        flags = (self.urg << 5 | self.ack << 4 | self.psh << 3 | self.rst << 2 | self.syn << 1 | self.fin)

        # Pack the header fields into a binary format
        header_data = struct.pack(
            '!HHIIBBHHH',
            self.sport,       # Source Port
            self.dport,       # Destination Port
            self.seqno,       # Sequence Number
            self.ackno,       # Acknowledgment Number
            (self.doff << 4) | 0,  # Data Offset (4 bits) and Reserved (4 bits)
            flags,            # Flags (6 bits) and Reserved (2 bits)
            self.win,         # Window
            0,                # Checksum
            self.uptr         # Urgent Pointer
        )
        cksum = tcp_checksum(src_ip, dst_ip, header_data, payload_data)
        self.cksum = cksum
        header_data = header_data[:16] + struct.pack('!H', cksum) + header_data[18:]
        return header_data

    @classmethod
    def deserialize(cls, src_ip: str, dst_ip: str, data: bytes) -> Optional['TcpHeader']:
        header_data = data[:TCP_HEADER_LENGTH]
        origin_header_data = header_data[:16] + b'\x00\x00' + header_data[18:]
        payload_data = data[TCP_HEADER_LENGTH:]
        cksum = tcp_checksum(src_ip, dst_ip, origin_header_data, payload_data)
        if cksum != struct.unpack('!H', header_data[16:18])[0]:
            return None

        fields = struct.unpack('!HHIIBBHHH', header_data)
        doff_reserved = fields[4]
        flags = fields[5]
        urg = bool(flags & 0x20)
        ack = bool(flags & 0x10)
        psh = bool(flags & 0x08)
        rst = bool(flags & 0x04)
        syn = bool(flags & 0x02)
        fin = bool(flags & 0x01)

        hdr = cls()
        hdr.sport = fields[0]
        hdr.dport = fields[1]
        hdr.seqno = fields[2]
        hdr.ackno = fields[3]
        hdr.doff = doff_reserved >> 4
        hdr.urg = urg
        hdr.ack = ack
        hdr.psh = psh
        hdr.rst = rst
        hdr.syn = syn
        hdr.fin = fin
        hdr.win = fields[6]
        hdr.cksum = fields[7]
        hdr.uptr = fields[8]

        return hdr


class TcpSegment:
    def __init__(
        self,
        header: TcpHeader,
        payload: bytes = b'',
        src_ip: str = '',
        dst_ip: str = ''
    ):
        self.header = header
        self.payload = payload
        self.src_ip = src_ip
        self.dst_ip = dst_ip

    def serialize(self) -> bytes:
        return self.header.serialize(self.src_ip, self.dst_ip, self.payload) + self.payload

    @classmethod
    def deserialize(
        cls,
        src_ip: str,
        dst_ip: str,
        data: bytes,
    ) -> Optional['TcpSegment']:
        header_data = data[:TCP_HEADER_LENGTH]
        header = TcpHeader.deserialize(src_ip, dst_ip, header_data)
        if not header:
            return None
        payload = data[TCP_HEADER_LENGTH:]
        seg = cls(header, payload, '', '')
        return seg

    @property
    def length_in_sequence_space(self) -> int:
        return len(self.payload) + int(self.header.syn) + int(self.header.fin)


if __name__ == '__main__':
    # s1 = TcpSegment(TcpHeader())
    # s1.header.syn = True
    # s1.header.fin = True
    # s2 = TcpSegment(TcpHeader())
    # print(s2.header.fin, s2.header.syn)
    # debug code
    header = TcpHeader()
    header.sport = 12345
    header.dport = 80
    header.seqno = 1000
    header.ackno = 2000
    header.urg = True
    header.ack = True
    header.psh = True
    header.win = 8192
    header.uptr = 0

    src_ip = '192.168.1.1'
    dst_ip = '192.168.1.2'
    payload = b''
    seg = TcpSegment(header, payload, src_ip, dst_ip)
    serialized_seg = seg.serialize()
    print("Serialized:", serialized_seg)
    seg2 = TcpSegment.deserialize(src_ip, dst_ip, serialized_seg)
    assert seg2
    for f, v in header.__dict__.items():
        # print(f, v, seg2.header.__dict__[f])
        assert v == seg2.header.__dict__[f]
    assert seg.payload == seg2.payload

