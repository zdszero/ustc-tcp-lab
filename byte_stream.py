class ByteStream:
    def __init__(self, capacity: int) -> int:
        self._capacity = capacity
        self._buffer = b''
        self._error = False
        self._bytes_written = 0
        self._bytes_read = 0
        self._end_write = False

    def write(self, data: bytes) -> int:
        if type(data) is str:
            data = bytes(data, 'utf-8')
        write_size: int
        if len(data) <= self.remaining_capacity:
            self._buffer += data
            write_size = len(data)
        else:
            write_size = self.capacity - len(self._buffer)
            self._buffer += data[:write_size]
        self._bytes_written += write_size
        return write_size

    def read(self, n: int) -> bytes:
        data = b''
        if n > self.size:
            self._error = True
            return data
        data = self._buffer[:n]
        self._buffer = self._buffer[n:]
        self._bytes_read += n
        return data

    def peek_output(self, size: int) -> bytes:
        peek_len = min(size, self.size)
        return self._buffer[:peek_len]

    def pop_output(self, size: int):
        if size > self.size:
            self._error = True
            return
        self._buffer = self._buffer[size:]
        self._bytes_read += size

    def end_input(self):
        self._end_write = True

    @property
    def error(self):
        return self._error
    
    @error.setter
    def error(self, val):
        self._error = val

    @property
    def input_ended(self) -> bool:
        return self._end_write

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def bytes_read(self) -> int:
        return self._bytes_read

    @property
    def empty(self) -> bool:
        return len(self._buffer) == 0

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def capacity(self):
        return self._capacity

    @property
    def remaining_capacity(self) -> int:
        return self._capacity - self.size

    @property
    def eof(self) -> bool:
        return self.empty and self._end_write
