import struct
import fcntl
import struct
import os
from abc import ABC, abstractmethod
from typing import Optional

from config import FdAdapterConfig
from tcp_segment import TcpSegment
from ipv4 import IPv4Datagram, IPv4Header

class FdAdapter(ABC):
    def __init__(self):
        self.config: Optional[FdAdapterConfig] = None
        self.listening = False

    @abstractmethod
    def read(self) -> Optional[TcpSegment]:
        pass

    @abstractmethod
    def write(self, seg: TcpSegment):
        pass

    @abstractmethod
    def fileno(self) -> int:
        pass

    def tick(self, ms_since_last: int):
        pass


class TcpOverUdpAdapter(FdAdapter):
    pass


# Constants for ioctl
TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000


class TcpOverIpv4OverTunAdapter(FdAdapter):
    def __init__(self, ifname: str):
        super().__init__()
        try:
            # Open the TUN device file
            self.tun = os.open('/dev/net/tun', os.O_RDWR)
            # Configure the TUN interface
            ifr = struct.pack('16sH', ifname.encode('utf-8'), IFF_TUN | IFF_NO_PI)
            fcntl.ioctl(self.tun, TUNSETIFF, ifr)
        except OSError as e:
            # Handle exceptions (e.g., log the error, re-raise, etc.)
            print(f"Failed to set up TUN interface: {e}")
            if hasattr(self, 'tun'):
                os.close(self.tun)
            raise

    def read(self) -> Optional[TcpSegment]:
        assert self.config
        recv_data = os.read(self.tun, 65535)
        ip_dgram = IPv4Datagram.deserialize(recv_data)
        if not ip_dgram:
            return None
        if not self.listening and ip_dgram.header.dst_ip != self.config.saddr:
            return None
        if not self.listening and ip_dgram.header.src_ip != self.config.daddr:
            return None
        if ip_dgram.header.proto != IPv4Header.PROTO_TCP:
            return None
        seg = TcpSegment.deserialize(ip_dgram.payload,
                                     src_ip=ip_dgram.header.src_ip,
                                     dst_ip=ip_dgram.header.dst_ip)
        if not seg:
            return None
        if self.listening:
            if seg.header.syn and not seg.header.rst:
                self.config.saddr = ip_dgram.header.dst_ip
                self.config.sport = seg.header.dport
                self.config.daddr = ip_dgram.header.src_ip
                self.config.dport = seg.header.sport
                self.listening = False
            else:
                return None
        if seg.header.dport != self.config.sport:
            return None

        return seg

    def write(self, seg: TcpSegment):
        assert self.config
        seg.header.sport = self.config.sport
        seg.header.dport = self.config.dport
        seg.src_ip = self.config.saddr
        seg.dst_ip = self.config.daddr
        ip_dgram = IPv4Datagram(
            IPv4Header(
                src_ip = self.config.saddr,
                dst_ip = self.config.daddr
            ),
            seg.serialize()
        )
        os.write(self.tun, ip_dgram.serialize())

    def fileno(self) -> int:
        return self.tun
