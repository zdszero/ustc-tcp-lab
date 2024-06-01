import struct


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

HEADER_LENGTH = 20
DEFAULT_TTL = 128
PROTO_TCP = 6


class IPv4Header:
    ver = 4
    hlen = HEADER_LENGTH // 4
    tos = 0
    len = 0
    id = 0
    df = True
    mf = False
    offset = 0
    ttl = DEFAULT_TTL
    proto = PROTO_TCP
    cksum = 0
    src_ip = '0.0.0.0'
    dst_ip = '0.0.0.0'

    def payload_len(self) -> int:
        return self.len - 4 * self.hlen

    def serialize(self):
        if self.ver != 4:
            raise ValueError('wrong IP version')

        if 4 * self.hlen < HEADER_LENGTH:
            raise ValueError('IP header too short')

        ver_hlen = (self.ver << 4) + self.hlen
        flags_offset = (self.df << 14) + (self.mf << 13) + self.offset

        header = struct.pack(
            "!BBHHHBBHII",
            ver_hlen,
            self.tos,
            self.len,
            self.id,
            flags_offset,
            self.ttl,
            self.proto,
            0,
            inet_aton(self.src_ip),
            inet_aton(self.dst_ip),
        )
        cksum = checksum(header)
        header = header[:10] + struct.pack('!H', cksum) + header[12:]
        return header

    @classmethod
    def deserialize(cls, data):
        fields = struct.unpack("!BBHHHBBHII", data)
        hdr = cls()
        hdr.ver = fields[0] >> 4
        hdr.hlen = fields[0] & 0x0f
        hdr.tos = fields[1]
        hdr.len = fields[2]
        hdr.id = fields[3]
        hdr.df = bool(fields[4] & 0x4fff)
        hdr.mf = bool(fields[4] & 0x2fff)
        hdr.offset = fields[4] & 0x1fff
        hdr.ttl = fields[5]
        hdr.proto = fields[6]
        hdr.cksum = fields[7]
        hdr.src_ip = inet_ntoa(data[12:16])
        hdr.dst_ip = inet_ntoa(data[16:20])
        return hdr


if __name__ == '__main__':
    header = IPv4Header()
    header.ver = 4
    header.hlen = 5
    header.tos = 0
    header.len = 0
    header.id = 0
    header.df = True
    header.mf = False
    header.offset = 0
    header.ttl = 64
    header.proto = 6
    header.src_ip = "192.168.1.1"
    header.dst_ip = "192.168.1.2"
    header.len = HEADER_LENGTH
    serialized_data = header.serialize()
    print(serialized_data)
    header2 = IPv4Header.deserialize(serialized_data)
    for f, v in header.__dict__.items():
        # print(v, header2.__dict__[f])
        assert v == header2.__dict__[f]
