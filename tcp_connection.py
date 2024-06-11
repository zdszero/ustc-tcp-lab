from collections import deque
from random import randint
from typing import Deque, Optional

from logger import log
from utils import wrap, unwrap, uint32_plus
from stream_reassembler import StreamReassembler
from byte_stream import ByteStream
from config import TcpConfig
from tcp_state import TcpState
from tcp_segment import TcpSegment, TcpHeader


class TcpConnection:
    def __init__(self,
                 cfg: TcpConfig,
                 sender_isn: int = randint(0, (1 << 32) - 1)):
        # General
        self._state = TcpState.CLOSED
        self._send_capacity = cfg.send_capacity
        self._recv_capacity = cfg.recv_capacity
        self._max_payload_size = cfg.MAX_PAYLOAD_SIZE
        self._max_retx_attempts = cfg.MAX_RETX_ATTEMPTS
        self._retx_timeout = cfg.TIMEOUT_DFLT
        self._active = True
        # For sender
        self._sender_isn = sender_isn
        self._next_seqno_absolute = 0
        self._receiver_window_size = 0
        self._timer_enabled = False
        self._time_elapsed = 0
        self._segments_out: Deque[TcpSegment] = deque()
        self._outgoing_segments: Deque[TcpSegment] = deque()
        self._consecutive_retransmissions = 0
        self._rto = cfg.rt_timeout
        self._stream_in = ByteStream(self._send_capacity)
        self._linger_after_stream_finish = False
        self._fin_sent = False
        # For receiver
        self._receiver_isn: Optional[int] = None
        self._reassembler = StreamReassembler(self._recv_capacity)
        self._fin_received = False

    def connect(self):
        if self._state != TcpState.CLOSED:
            raise RuntimeError(
                'tcp state is not closed when calling connect()')
        self._send_segment(TcpSegment(TcpHeader(
            syn=True,
            seqno=self._sender_isn
        )))
        self._state = TcpState.SYN_SENT

    def write(self, data: bytes) -> int:
        if len(data) == 0:
            return 0
        write_size = self._stream_in.write(data)
        self._fill_window()
        return write_size

    def set_listening(self):
        if self._state != TcpState.CLOSED:
            raise RuntimeError(
                'tcp state is not closed when calling set_listening()')
        self._state = TcpState.LISTEN

    def segment_received(self, seg: TcpSegment):
        try:
            callback = {
                TcpState.CLOSED: self._fsm_closed,
                TcpState.LISTEN: self._fsm_listen,
                TcpState.SYN_SENT: self._fsm_syn_sent,
                TcpState.SYN_RECEIVED: self._fsm_syn_received,
                TcpState.ESTABLISHED: self._fsm_eastablished,
                TcpState.CLOSE_WAIT: self._fsm_closed_wait,
                TcpState.LAST_ACK: self._fsm_last_ack,
                TcpState.FIN_WAIT_1: self._fsm_fin_wait_1,
                TcpState.FIN_WAIT_2: self._fsm_fin_wait_2,
                TcpState.CLOSING: self._fsm_closing,
                TcpState.TIME_WAIT: self._fsm_time_wait
            }[self._state]
            callback(seg)
        except KeyError as _:
            raise RuntimeError(f'Unknown tcp state: {self._state}')

    def _fsm_closed(self, seg: TcpSegment):
        pass

    def _fsm_listen(self, seg: TcpSegment):
        if not seg.header.syn:
            return
        self._receiver_isn = seg.header.seqno
        self._send_segment(TcpSegment(TcpHeader(
            syn=True,
            ack=True,
            ackno=uint32_plus(seg.header.seqno),
            seqno=self._sender_isn
        )))
        self._state = TcpState.SYN_RECEIVED

    def _fsm_syn_sent(self, seg: TcpSegment):
        expected_ackno = uint32_plus(self._sender_isn)
        if not (
            seg.header.syn and
            seg.header.ack and
            seg.header.ackno == expected_ackno
        ):
            return
        self._receiver_isn = seg.header.seqno
        self._send_segment(TcpSegment(TcpHeader(
            ack=True,
            ackno=uint32_plus(seg.header.seqno, 1)
        )))
        self._state = TcpState.ESTABLISHED

    def _fsm_syn_received(self, seg: TcpSegment):
        assert self._receiver_isn
        if not (
            seg.header.ack and
            seg.header.seqno == uint32_plus(self._receiver_isn) and
            seg.header.ackno == uint32_plus(self._sender_isn)
        ):
            return
        self._receiver_window_size = seg.header.win
        self._state = TcpState.ESTABLISHED

    def _fsm_eastablished(self, seg: TcpSegment):
        # receiver operation
        seqno = seg.header.seqno
        seqno_absolute = self._unwrap_receiver(seqno)
        stream_index = seqno_absolute - int(self.syn_received)
        eof = seg.header.fin
        if eof:
            self._state = TcpState.CLOSE_WAIT
            self._fin_received = True
            log('FSM', f'receive FIN at {stream_index}')
        if len(seg.payload) > 0:
            log('FSM', f'receive data at {stream_index} with payload length {len(seg.payload)}')
            self._reassembler.data_received(stream_index, seg.payload, eof)
            assert self.ackno
            self._send_segment(TcpSegment(TcpHeader(
                ack=True,
                ackno=self.ackno
            )))
        # sender operation
        if seg.header.ack:
            self._receiver_window_size = seg.header.win
            self._ack_received(seg.header.ackno)

    def _fsm_closed_wait(self, seg: TcpSegment):
        if self.unassembled_bytes > 0:
            self._fsm_eastablished(seg)
        if (
            self._state == TcpState.CLOSE_WAIT and
            self.inbound_stream.eof and
            self.bytes_in_flight == 0 and
            self._reassembler.finished
        ):
            seg = TcpSegment(TcpHeader(fin=True))
            self._send_segment(seg)
            self._state = TcpState.LAST_ACK

    def _fsm_last_ack(self, seg: TcpSegment):
        expected_ackno = self._wrap_sender(self._next_seqno_absolute)
        if not (
            seg.header.ack and
            seg.header.ackno == expected_ackno
        ):
            return
        self._state = TcpState.CLOSED

    def _fsm_fin_wait_1(self, seg: TcpSegment):
        expected_ackno = self._wrap_sender(self._next_seqno_absolute)
        if not (
            seg.header.ack and
            seg.header.ackno == expected_ackno
        ):
            return
        if seg.header.fin:
            self._state = TcpState.CLOSING
        else:
            self._state = TcpState.FIN_WAIT_2

    def _fsm_fin_wait_2(self, seg: TcpSegment):
        if (
            seg.header.fin and
            seg.header.seqno == self.ackno
        ):
            assert self.ackno
            self._fin_received = True
            self._send_segment(TcpSegment(TcpHeader(
                ack=True,
                ackno=self.ackno
            )))
            self._state = TcpState.TIME_WAIT

    def _fsm_closing(self, seg: TcpSegment):
        pass

    def _fsm_time_wait(self, seg: TcpSegment):
        pass

    def _wrap_sender(self, n: int) -> int:
        return wrap(n, self._sender_isn)

    def _wrap_receiver(self, n: int) -> int:
        assert self._receiver_isn
        return wrap(n, self._receiver_isn)

    def _unwrap_sender(self, n: int) -> int:
        return unwrap(n, self._sender_isn, self._next_seqno_absolute)

    def _unwrap_receiver(self, n: int) -> int:
        checkpoint = self._reassembler.ack_index
        assert self._receiver_isn
        return unwrap(n, self._receiver_isn, checkpoint)

    def _ack_received(self, ackno: int):
        """
        Remove acked segments from outgoing
        Reset timer
        """
        def ack_valid(ackno_absolute: int) -> bool:
            if not self._outgoing_segments:
                return ackno_absolute <= self._next_seqno_absolute
            first_seqno_absolute = self._unwrap_sender(
                self._outgoing_segments[0].header.seqno)
            return first_seqno_absolute <= ackno_absolute <= self._next_seqno_absolute

        ackno_absolute = self._unwrap_sender(ackno)
        if not ack_valid(ackno_absolute):
            return
        while self._outgoing_segments:
            seg = self._outgoing_segments[0]
            expected_ackno_absolute = self._unwrap_sender(
                seg.header.seqno + seg.length_in_sequence_space)
            if ackno_absolute >= expected_ackno_absolute:
                self._outgoing_segments.popleft()
                self._rto = self._retx_timeout
                self._consecutive_retransmissions = 0
                self._time_elapsed = 0
            else:
                break
        if not self._outgoing_segments:
            self._timer_enabled = False
        self._fill_window()

    def _send_segment(
        self,
        seg: TcpSegment,
    ):
        self._next_seqno_absolute += seg.length_in_sequence_space
        seg.header.win = self.window_size
        self._segments_out.append(seg)
        if len(seg.payload) > 0:
            self._outgoing_segments.append(seg)
        if not self._timer_enabled:
            self._timer_enabled = True
            self._time_elapsed = 0
        seg_attrs = []
        if seg.header.ack:
            seg_attrs.append('ack=1')
            seg_attrs.append(f'ackno={self.ackno}')
        if len(seg.payload) > 0:
            seg_attrs.append(f'payload_len={len(seg.payload)}')
        log('FSM', 'send segment with ' + ','.join(seg_attrs))

    @property
    def available_receiver_space(self):
        if len(self._outgoing_segments) == 0:
            return self._receiver_window_size
        window_left = self._unwrap_sender(self._outgoing_segments[0].header.seqno)
        window_right = window_left + self._receiver_window_size
        available_space = window_right - self._next_seqno_absolute
        return available_space

    def _fill_window(self):
        if self.fin_sent:
            return
        send_size = min(self._stream_in.size + int(self._stream_in.input_ended),
                        self.available_receiver_space)
        assert send_size >= 0
        while send_size > 0:
            payload_size = min(send_size - int(self._stream_in.input_ended),
                               self._max_payload_size)
            payload = self._stream_in.read(payload_size)
            assert not self._stream_in.error
            seg = TcpSegment(TcpHeader(
                seqno = self._wrap_sender(self._next_seqno_absolute)
            ), payload)
            send_size -= payload_size
            if self._stream_in.eof and send_size > 0:
                seg.header.fin = True
                self._state = TcpState.FIN_WAIT_1
                self._fin_sent = True
                send_size -= 1
            self._send_segment(seg)

    def tick(self, ms_since_last_tick: int):
        if not self._timer_enabled:
            return
        self._time_elapsed += ms_since_last_tick
        if self._time_elapsed >= self._rto:
            if self._consecutive_retransmissions >= self._max_retx_attempts:
                self._stream_in.error = True
                self._reassembler._stream_out.error = True
                self._send_segment(TcpSegment(TcpHeader(
                    rst=True
                )))
                self._active = False
                return
            assert self._outgoing_segments
            self._segments_out.append(self._outgoing_segments[0])
            if self._receiver_window_size:
                self._rto = (self._rto << 1)
            self._timer_enabled = True
            self._time_elapsed = 0
            self._consecutive_retransmissions += 1

    def shutdown_write(self):
        self._stream_in.end_input()
        self._fill_window()

    @property
    def state(self) -> int:
        return self._state

    @property
    def syn_received(self) -> bool:
        return self._receiver_isn is not None

    @property
    def fin_sent(self):
        return self._fin_sent

    @property
    def fin_received(self) -> bool:
        return self._fin_received

    @property
    def bytes_in_flight(self) -> int:
        return sum(seg.length_in_sequence_space for seg in self._outgoing_segments)

    @property
    def consecutive_retransmissions(self):
        return self._consecutive_retransmissions

    @property
    def next_seqno(self) -> int:
        return wrap(self._next_seqno_absolute, self._sender_isn)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def unassembled_bytes(self) -> int:
        return self._reassembler.unassembled_bytes

    @property
    def assembled_bytes(self) -> int:
        return self._reassembler.stream_out.bytes_written

    @property
    def outbound_stream(self) -> ByteStream:
        return self._reassembler.stream_out

    @property
    def inbound_stream(self) -> ByteStream:
        return self._stream_in

    @property
    def segments_out(self):
        return self._segments_out

    @property
    def window_size(self) -> int:
        return self._recv_capacity - self._reassembler.stream_out.size

    @property
    def ackno(self) -> Optional[int]:
        if not self.syn_received:
            return None
        assert self._receiver_isn
        return self._wrap_receiver(1 + self._reassembler.ack_index + int(self.fin_received))
