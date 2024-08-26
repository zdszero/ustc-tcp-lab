import selectors
from typing import Callable
from threading import Thread
from typing import Optional
import os
import random
from logger import log
from event_loop import EventLoop, SocketPair
from tcp_connection import TcpConnection
from tcp_state import TcpState
from config import TcpConfig, FdAdapterConfig
from fd_adapter import FdAdapter,TcpOverIpv4OverTunAdapter
from utils import timestamp_ms

TCP_TICK_MS = 10

class TcpSocket:
    def __init__(self, datagram_adapater: FdAdapter):
        # self.thread_data = io.BytesIO()
        # r_fd,w_fd=os.pipe()
        self.thread_data = SocketPair()
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

    def connect(self):
        self._init_tcp()
        self._tcp.connect()
        if self._tcp._state != TcpState.SYN_SENT:
            raise RuntimeError(f'Tcp state is not SYN_SENT after calling connect()')
        self._tcp_loop(lambda: self._tcp.state == TcpState.SYN_SENT)
        # print(f'Successfully connected to {adapter_cfg.daddr}:{adapter_cfg.dport}')
        self._tcp_thread = Thread(target=self._tcp_main)
        self._tcp_thread.start()

    def listen_and_accept(self, adapter_cfg: FdAdapterConfig):
        self._init_tcp()
        self._tcp.set_listening()
        self._tcp_loop(lambda: self._tcp.state in [TcpState.LISTEN, TcpState.SYN_RECEIVED])
        # print(f'Successfully receive connection from {adapter_cfg.daddr}:{adapter_cfg.dport}')
        self._tcp_thread = Thread(target=self._tcp_main, args=[self])
        self._tcp_thread.start()

    def _tcp_main(self):
        try:
            assert self._tcp
            self._tcp_loop(lambda:True)
            os.close(self._adapter.fileno())
            self.thread_data.parent_sock.close()
            self.thread_data.child_sock.close()
            if not self._tcp.active:
                print("DEBUG: TCP connection finished")
        except Exception as e:
            print(f"Exception in TCPConnection runner thread: {e}")
            raise

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
        """
        Condition 1: adapter is readable
            receive segment from peer
        """
        assert self._tcp
        def on_adapter_readable():
            seg = self._adapter.read()
            if seg:
                self._tcp.segment_received(seg)
            if self.thread_data.closed and self._tcp.bytes_in_flight == 0 and not self.fully_acked:
                self.fully_acked = True
            # log("FSM","adapter -> tcp")
        self._loop.add_rule(
            self._adapter,
            selectors.EVENT_READ,
            callback=on_adapter_readable,
            interest=lambda: self._tcp.active
        )

        """
        Condition 2: adapter is writable
            write available segments
        """
        def on_adapter_writable():
            while self._tcp.segments_out:
                self._adapter.write(self._tcp.segments_out.popleft())
            # log("FSM","tcp -> adapter")
        self._loop.add_rule(
            self._adapter,
            selectors.EVENT_WRITE,
            callback=on_adapter_writable,
            interest=lambda: len(self._tcp._segments_out) > 0
        )

        """
        Condition 3: thread is readable
            read data from thread and write these data into tcp
        """
        def on_thread_readable():
            remaining_capacity = self._tcp.inbound_stream.remaining_capacity
            # data = self.thread_data.read(remaining_capacity)
            data = self.thread_data.recv(remaining_capacity)
            amount_written = self._tcp.write(data)
            # log("FSM","thread -> tcp")
            if amount_written != len(data):
                raise RuntimeError(
                    'TcpConnection.write() accept less than advertised length')
            if self.thread_data.closed:
                self._tcp.shutdown_write()
                self.outbound_shutdown = True

        def thread_read_cancelled():
            self._tcp.shutdown_write()
            self.outbound_shutdown = True

        self._loop.add_rule(
            self.thread_data,
            selectors.EVENT_READ,
            callback=on_thread_readable,
            interest=lambda: (
                self._tcp.active and
                not self.outbound_shutdown and
                self._tcp.inbound_stream.remaining_capacity > 0
            ),
            cancel=thread_read_cancelled
        )

        """
        Condition 4: thread is writable
        """
        def on_thread_writable():
            outbound = self._tcp.outbound_stream
            amount_to_write = min(65535, outbound.size)
            buf = outbound.peek_output(amount_to_write)
            bytes_written = self.thread_data.send(buf)
            outbound.pop_output(bytes_written)
            # log("FSM","tcp -> thread")
            if outbound.error or outbound.eof:
                self.thread_data.close()
                self.inbound_shutdown = True

        def thread_write_interest():
            outbound = self._tcp.outbound_stream
            return outbound.size > 0 and not outbound.eof and not outbound.error and not self.inbound_shutdown

        self._loop.add_rule(
            self.thread_data,
            selectors.EVENT_WRITE,
            callback=on_thread_writable,
            interest=thread_write_interest
        )

    def send(self, data: bytes):
        self.thread_data.child_sock.send(data)

    def recv(self, buf_size: int) -> bytes:
        return self.thread_data.child_sock.recv(buf_size)

    def close(self):
        self._tcp.shutdown_write()
        while(self._tcp.active):
            pass
        self._abort=True
        if self._tcp_thread:
            self._tcp_thread.join()

class Address:
    def __init__(self, ip, port = 80):
        self.ip = ip
        self.port = port 

class FullTCPSocket(TcpSocket):
    def __init__(self):
        super().__init__(TcpOverIpv4OverTunAdapter('tun144'))
    
    def connect(self,address:Address):
        multiplexer_config=FdAdapterConfig(
            saddr="169.254.144.9",
            sport=random.randint(0, 65535),
            daddr=address.ip,
            dport=address.port
        )
        super().connect(multiplexer_config)
