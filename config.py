from dataclasses import dataclass

ENABLED_CHANNELS = [
    'FSM'
]

@dataclass
class TcpConfig:
    # ByteStream
    DEFAULT_CAPACITY = 64000
    # payload最多包含1000字节
    MAX_PAYLOAD_SIZE = 1000
    # 超时重传的时间为1000ms
    TIMEOUT_DFLT = 1000
    # 最大重传次数为8
    MAX_RETX_ATTEMPTS = 8

    rt_timeout = TIMEOUT_DFLT
    recv_capacity = DEFAULT_CAPACITY
    send_capacity = DEFAULT_CAPACITY

    MSL = 1000 * 120


@dataclass
class FdAdapterConfig:
    sport: int
    dport: int
    saddr: str
    daddr: str

    loss_rate_dn: int = 0
    loss_rate_up: int = 0
