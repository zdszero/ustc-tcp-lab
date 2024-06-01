import socket
from typing import Optional

from config import FdAdapterConfig
from tcp_segment import TcpSegment


class FdAdapterBase:
    def __init__(self):
        self._config = FdAdapterConfig()
        self._listen = False

    @property
    def config(self):
        return self._config

    @property
    def listening(self):
        return self._listen

    @listen.setter
    def listen(self, val: bool):
        self._listen = val


class TcpOverUdpSocketAdapter(FdAdapterBase):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def read(self) -> Optional[TcpSegment]:
        data, (peer_ip, _) = self.sock.recvfrom()
        local_ip = self.sock.getsockname()[0]
        seg = TcpSegment.deserialize(peer_ip, local_ip, data)
        if not seg:
            return None
        return seg

    def write(self, seg: TcpSegment):
        seg.header.sport = self._config.sport
        seg.header.dport = self._config.dport
        self.sock.sendto(seg.serialize(), (seg.dst_ip, seg.header.dport))
