import time
from typing import Optional, Any, List


PROGRAM_START: Optional[float] = None
UINT32_MAX = 0xffffffff
uint32 = int
uint64 = int


def inet_aton(ipv4_addr: str) -> bytes:
    octets: List[Any] = ipv4_addr.split('.')
    if len(octets) != 4:
        raise ValueError("Invalid IPv4 address format")
    for i in range(4):
        octets[i] = int(octets[i])
        if octets[i] < 0 or octets[i] > 255:
            raise ValueError("Each octet must be between 0 and 255")
    address = (octets[0] << 24) | (
        octets[1] << 16) | (octets[2] << 8) | octets[3]
    return address


def inet_ntoa(packed_id: bytes):
    if len(packed_id) != 4:
        raise ValueError('invalid IP address')
    return '.'.join(map(str, packed_id))


def checksum(header: bytes):
    if len(header) % 2 != 0:
        header += b'\0'
    cksum = 0
    for i in range(0, len(header), 2):
        part = header[i] << 8 | header[i + 1]
        cksum += part
        cksum = (cksum & 0xffff) + (cksum >> 16)
    cksum = ~cksum & 0xffff
    return cksum


def timestamp_ms():
    global PROGRAM_START
    if not PROGRAM_START:
        PROGRAM_START = time.perf_counter()
    now = time.perf_counter()
    elapsed_ms = (now - PROGRAM_START) * 1000
    return int(elapsed_ms)


def wrap(n: uint64, isn: uint32) -> uint32:
    """
    convert absolute seqno to seqno
    """
    return (n + isn) & 0xffffffff


def unwrap(n: uint32, isn: uint32, checkpoint: uint64):
    """
    convert seqno to absolute seqno
    """
    c: uint32 = wrap(checkpoint, isn)
    tmp1, tmp2 = 0, 0
    if n >= c:
        tmp1 = checkpoint + (n - c)
        tmp2 = checkpoint - ((1 << 32) - (n - c))
    else:
        tmp1 = checkpoint + ((1 << 32) - (c - n))
        tmp2 = checkpoint - (c - n)
    # tmp2 < tmp1
    if tmp2 < 0:
        return tmp1
    return tmp1 if abs(tmp1 - checkpoint) < abs(tmp2 - checkpoint) else tmp2


def uint32_plus(n: uint32, x: uint32 = 1):
    return (n + x) % (1 << 32)
