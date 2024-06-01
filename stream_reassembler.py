from collections import deque
from typing import Deque, Tuple

from byte_stream import ByteStream


class StreamReassembler:
    def __init__(
        self,
        capacity: int
    ):
        self._capacity = capacity
        self._unassembled_base = 0
        self._buffer: Deque[Tuple[int, bytes]] = deque()
        self._eof = False
        self._stream_out = ByteStream(capacity)

    """
    |   1   |   2   |   3   |   4   |
    |----> window size <----|

    1: assembled but not received data (application layer should use read() to read these data)
    2. data not received
    3. unassembled data
    4. data that cannot be put in buffer
    """

    def data_received(self, index: int, data: bytes, eof: bool):
        if eof:
            self._eof = True
        # data 开始和结束
        first = index
        last = first + len(data)
        # 窗口开始和结束
        window_begin = self._unassembled_base - self._stream_out.size
        window_end = window_begin + self._capacity
        if last <= self._unassembled_base or first >= window_end:
            return
        # 需要放入 buffer 的数据开始和结束
        left = max(first, self._unassembled_base)
        right = min(last, window_end)
        # 最后需要转化为相对于 first 的下标
        buffer_data = data[left-first:right-first]
        place = 0
        for i, _ in self._buffer:
            if left <= i:
                break
            place += 1
        self._buffer.insert(place, (left, buffer_data))
        self._merge()
        if self._buffer and self._buffer[0][0] == self._unassembled_base:
            self._stream_out.write(self._buffer[0][1])
            self._unassembled_base += len(self._buffer[0][1])
            self._buffer.popleft()
        if self.finished:
            self._stream_out.end_input()

    def _merge(self):
        if len(self._buffer) == 0:
            return
        assert self._buffer[0][0] >= self._unassembled_base
        i = 0
        while i < len(self._buffer) - 1:
            a, d1 = self._buffer[i]
            b = a + len(d1)
            c, d2 = self._buffer[i + 1]
            d = c + len(d2)
            assert a <= c
            if c > b:
                i += 1
            else:
                if b >= d:
                    del self._buffer[i + 1]
                else:
                    self._buffer[i] = (a, d1 + d2[b - c:])

    @property
    def finished(self) -> bool:
        return self._eof and self.unassembled_bytes == 0

    @property
    def ack_index(self):
        return self._unassembled_base

    @property
    def stream_out(self) -> ByteStream:
        return self._stream_out

    @property
    def unassembled_bytes(self) -> int:
        return sum(len(data) for _, data in self._buffer)

    @property
    def assembled_bytes(self) -> int:
        return self._stream_out.bytes_written
