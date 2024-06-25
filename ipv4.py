import struct
from typing import Optional

from utils import checksum, inet_aton, inet_ntoa


"""
     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |Version|  IHL  |Type of Service|          Total Length         |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |         Identification        |Flags|      Fragment Offset    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |  Time to Live |    Protocol   |         Header Checksum       |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                       Source Address                          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                    Destination Address                        |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                    Options                    |    Padding    |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
"""


class IPv4Header:
    HEADER_LENGTH = 20
    DEFAULT_TTL = 128
    PROTO_TCP = 6
    identification_counter = 0

    def __init__(
        self,
        ver=4,
        ihl=HEADER_LENGTH // 4,
        tos=0,
        length=0,
        id=None,
        df=False,
        mf=False,
        offset=0,
        ttl=DEFAULT_TTL,
        proto=PROTO_TCP,
        cksum=0,
        src_ip='0.0.0.0',
        dst_ip='0.0.0.0'
    ):
        self.ver = ver
        self.ihl = ihl
        self.tos = tos
        self.length = length
        self.id = id if id is not None else self._get_next_id()
        self.df = df
        self.mf = mf
        self.offset = offset
        self.ttl = ttl
        self.proto = proto
        self.cksum = cksum
        self.src_ip = src_ip
        self.dst_ip = dst_ip

    @classmethod
    def _get_next_id(cls):
        cls.identification_counter += 1
        # Ensure it wraps around within 16-bit range
        return cls.identification_counter % 65536

    @property
    def payload_len(self) -> int:
        return self.length - 4 * self.ihl

    def serialize(self):
        if self.ver != 4:
            raise ValueError('wrong IP version')

        if 4 * self.ihl < IPv4Header.HEADER_LENGTH:
            raise ValueError('IP header too short')

        ver_hlen = (self.ver << 4) | self.ihl
        flags_offset = (self.df << 14) | (self.mf << 13) | self.offset

        # Pack the IPv4 header fields into bytes
        # The '!' signifies network (= big-endian) order
        # 'B' stands for unsigned char (1 byte)
        # 'H' stands for unsigned short (2 bytes)
        # 'I' stands for unsigned int (4 bytes)
        header = struct.pack(
            "!BBHHHBBHII",
            ver_hlen,
            self.tos,
            self.length,
            self.id,
            flags_offset,
            self.ttl,
            self.proto,
            0,
            inet_aton(self.src_ip),
            inet_aton(self.dst_ip),
        )
        self.cksum = checksum(header)
        header = header[:10] + struct.pack('!H', self.cksum) + header[12:]
        return header

    @classmethod
    def deserialize(cls, data: bytes):
        fields = struct.unpack("!BBHHHBBHII", data)
        hdr = cls(
            ver=fields[0] >> 4,
            ihl=fields[0] & 0x0f,
            tos=fields[1],
            length=fields[2],
            id=fields[3],
            df=bool(fields[4] & 0x4000),
            mf=bool(fields[4] & 0x2000),
            offset=fields[4] & 0x1fff,
            ttl=fields[5],
            proto=fields[6],
            cksum=fields[7],
            src_ip=inet_ntoa(data[12:16]),
            dst_ip=inet_ntoa(data[16:20])
        )
        return hdr


class IPv4Datagram:
    def __init__(
        self,
        header: IPv4Header,
        payload: bytes
    ):
        self.header = header
        self.payload = payload

    def serialize(self):
        self.header.length = IPv4Header.HEADER_LENGTH + len(self.payload)
        return self.header.serialize() + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['IPv4Datagram']:
        if len(data) < IPv4Header.HEADER_LENGTH:
            return None
        hdr = IPv4Header.deserialize(data[:IPv4Header.HEADER_LENGTH])
        payload = data[IPv4Header.HEADER_LENGTH:]
        if hdr.payload_len != len(payload):
            return None
        return cls(hdr, payload)
