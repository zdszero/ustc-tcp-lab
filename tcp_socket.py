import selectors
from typing import Callable
from threading import Thread, Optional

from event_loop import EventLoop
from tcp_connection import TcpConnection
from tcp_state import TcpState
from config import TcpConfig, FdAdapterConfig
from utils import timestamp_ms

TCP_TICK_MS = 10


class TcpSocket:
    def __init__(self, thread_data, datagram_adapater):
        self.thread_data = thread_data
        self._adapter = datagram_adapater
        self._loop = EventLoop()
        self._abort = False
        self._cfg = TcpConfig()
        self._tcp = TcpConnection(self._cfg)
        self._tcp_thread: Optional[Thread] = None
        # has tcp socket shutdown the incoming data?
        self.inbound_shutdown = False
        # has tcp socket shutdown the outcoming data?
        self.outbound_shutdown = False
        # has the outbound data fully acknowledged by the peer?
        self.fully_acked = False

    def connect(self, adapter_cfg: FdAdapterConfig):
        self._init_tcp()
        self._tcp.connect()
        if self._tcp._state != TcpState.SYN_SENT:
            raise RuntimeError(f'Tcp state is not SYN_SENT after calling connect()')
        self._tcp_loop(lambda: self._tcp.state == TcpState.SYN_SENT)
        print(f'Successfully connected to {adapter_cfg.daddr}:{adapter_cfg.dport}')
        self._tcp_thread = Thread(target=self._tcp_main, args=[self])
        self._tcp_thread.run()

    def listen_and_accept(self, adapter_cfg: FdAdapterConfig):
        self._init_tcp()
        self._tcp.set_listening()
        self._tcp_loop(lambda: self._tcp.state in [TcpState.LISTEN, TcpState.SYN_RECEIVED])
        print(f'Successfully receive connection from {adapter_cfg.daddr}:{adapter_cfg.dport}')
        self._tcp_thread = Thread(target=self._tcp_main, args=[self])
        self._tcp_thread.run()

    def _tcp_main(self):
        pass

    def _tcp_loop(self, condition: Callable[[], bool]):
        base_time = timestamp_ms()
        while condition():
            ret = self._loop.wait_next_event(TCP_TICK_MS)
            if not ret or self._abort:
                break
            if self._tcp.active:
                next_time = timestamp_ms()
                self._tcp.tick(next_time - base_time)
                self._adapter.tick(next_time - base_time)
                base_time = next_time

    def _init_tcp(self):
        # 第1种情形：
        # 当适配器有数据可读时（即tcp peer发送segment到达本机），将segment放入tcp接收窗口中
        assert self._tcp
        def on_adapter_readable():
            seg = self._adapter.read()
            if seg:
                self._tcp.segment_received(seg)
            if self.thread_data.closed and self._tcp.bytes_in_flight == 0 and not self.fully_acked:
                self.fully_acked = True
        self._loop.add_rule(
            self._adapter,
            selectors.EVENT_READ,
            callback=on_adapter_readable,
            interest=lambda: self._tcp.active
        )

        # 第2种情形：
        # 当适配器有写入空间时，从tcp流中取出segment进行发送
        def on_adapter_writable():
            while self._tcp.segments_out:
                self._adapter.write(self._tcp.segments_out.popleft())

        # 条件是tcp的待发送segments不为空
        def adapter_write_interest() -> bool:
            return len(self._tcp.segments_out) > 0

        self._loop.add_rule(
            self._adapter,
            selectors.EVENT_WRITE,
            callback=on_adapter_writable,
            interest=adapter_write_interest
        )

        # 第3种情形：
        # 当应用层有数据到达时，将这些数据写入tcp流中
        def on_thread_readable():
            remaining_capacity = self._tcp.inbound_stream.remaining_capacity
            data = self.thread_data.read(remaining_capacity)
            amount_written = self._tcp.write(data)
            if amount_written != len(data):
                raise RuntimeError(
                    'TcpConnection.write() accept less than advertised length')
            if self.thread_data.closed:
                self._tcp.end_input_stream()
                self.outbound_shutdown = True

        def thread_read_interest() -> bool:
            return self._tcp.active and not self.outbound_shutdown and self._tcp.inbound_stream.remaining_capacity > 0

        def thread_read_cancelled():
            self._tcp.end_input_stream()
            self.outbound_shutdown = True

        self._loop.add_rule(
            self.thread_data,
            selectors.EVENT_READ,
            callback=on_thread_readable,
            interest=thread_read_interest,
            cancel=thread_read_cancelled
        )

        # 第4种情形：
        # 当应用层可以读取数据时，从tcp接收缓冲区读取数据
        def on_thread_writable():
            inbound = self._tcp.inbound_stream
            amount_to_write = min(65535, inbound.size)
            buf = inbound.peek_output(amount_to_write)
            bytes_written = self.thread_data.write(buf)
            inbound.pop_output(bytes_written)
            if inbound.error or inbound.eof:
                self.thread_data.shutdown(SHUT_WR)
                self.inbound_shutdown = True

        # 条件是tcp输入缓冲区有数据、没有错误、输入没有被关闭
        def thread_write_interest():
            inbound = self._tcp.inbound_stream
            return inbound.size > 0 and not inbound.eof and not inbound.error and not self.inbound_shutdown

        self._loop.add_rule(
            self.thread_data,
            selectors.EVENT_WRITE,
            callback=on_thread_writable,
            interest=thread_write_interest
        )
