import unittest
from stream_reassembler import StreamReassembler

import random

class TestReassembler(unittest.TestCase):
    def checkBuffer(self, reassembler: StreamReassembler, index: int, data: bytes, eof: bool, buffer: list):
        reassembler.data_received(index, data, eof)
        self.assertEqual(list(reassembler._buffer), buffer)

    def expectData(self, reassembler: StreamReassembler, data: bytes):
        size = reassembler.stream_out.size
        self.assertEqual(reassembler.stream_out.read(size), data)

    def test_exceeding_data(self):
        reassembler = StreamReassembler(2)
        self.checkBuffer(reassembler, 1, b'12', False, [(1, b'1')])
        self.checkBuffer(reassembler, 0, b'0', False, [])
        self.assertEqual(reassembler.assembled_bytes, 2)
        self.assertEqual(reassembler.unassembled_bytes, 0)
        self.assertEqual(reassembler.ack_index, 2)
        self.expectData(reassembler, b'01')
        self.checkBuffer(reassembler, 3, b'34', False, [(3, b'3')])
        self.checkBuffer(reassembler, 2, b'2', False, [])
        self.expectData(reassembler, b'23')
        self.assertEqual(reassembler.assembled_bytes, 4)
        self.assertEqual(reassembler.unassembled_bytes, 0)

    def test_outdated_data(self):
        reassembler = StreamReassembler(10)
        self.checkBuffer(reassembler, 1, b'12', False, [(1, b'12')])
        self.assertEqual(reassembler.assembled_bytes, 0)
        self.assertEqual(reassembler.unassembled_bytes, 2)
        self.assertEqual(reassembler.ack_index, 0)
        self.checkBuffer(reassembler, 1, b'123', False, [(1, b'123')])
        self.assertEqual(reassembler.assembled_bytes, 0)
        self.assertEqual(reassembler.unassembled_bytes, 3)
        self.assertEqual(reassembler.ack_index, 0)
        self.checkBuffer(reassembler, 0, b'0', False, [])
        self.assertEqual(reassembler.assembled_bytes, 4)
        self.assertEqual(reassembler.unassembled_bytes, 0)
        self.assertEqual(reassembler.ack_index, 4)
        self.checkBuffer(reassembler, 0, b'abcd456', False, [])
        self.assertEqual(reassembler.assembled_bytes, 7)
        self.assertEqual(reassembler.unassembled_bytes, 0)
        self.expectData(reassembler, b'0123456')

    def test_merge(self):
        reassembler = StreamReassembler(10)

        self.checkBuffer(reassembler, 1, b'12', False, [(1, b'12')])
        self.assertEqual(reassembler.unassembled_bytes, 2)
        self.checkBuffer(reassembler, 7, b'7890123',
                          False, [(1, b'12'), (7, b'789')])
        self.assertEqual(reassembler.unassembled_bytes, 5)
        self.checkBuffer(reassembler, 4, b'45', False, [
                          (1, b'12'), (4, b'45'), (7, b'789')])
        self.checkBuffer(reassembler, 6, b'6', False,
                          [(1, b'12'), (4, b'456789')])
        self.assertEqual(reassembler.unassembled_bytes, 8)
        self.checkBuffer(reassembler, 0, b'012', False, [(4, b'456789')])
        self.assertEqual(reassembler.stream_out.size, 3)
        self.assertEqual(reassembler._unassembled_base, 3)
        self.checkBuffer(reassembler, 0, b'012', False, [(4, b'456789')])
        self.checkBuffer(reassembler, 1, b'12', False, [(4, b'456789')])
        self.assertEqual(reassembler.stream_out.read(3), b'012')
        self.assertTrue(reassembler.stream_out.empty)
        self.checkBuffer(reassembler, 11, b'12', False,
                          [(4, b'456789'), (11, b'12')])
        self.checkBuffer(reassembler, 3, b'3', False, [(11, b'12')])
        self.assertEqual(reassembler.stream_out.size, 7)
        self.assertEqual(reassembler._unassembled_base, 10)
        self.checkBuffer(reassembler, 10, b'0123456', False, [])
        self.assertEqual(reassembler.stream_out.size, 10)
        self.assertEqual(reassembler.stream_out.read(10), b'3456789012')

    def test_capacity(self):
        reassembler = StreamReassembler(3)
        for i in range(0, 9997, 3):
            segment = "".join(
                [chr(i), chr(i + 1), chr(i + 2), chr(i + 13), chr(i + 47), chr(i + 9)]
            )
            segment = segment.encode()
            reassembler.data_received(i, segment, False)
            self.assertEqual(reassembler.assembled_bytes, i + 3)
            self.expectData(reassembler, segment[:3])

    def test_duplicate(self):
        reassembler = StreamReassembler(65000)
        self.checkBuffer(reassembler, 0, b"abcdefgh", False, [])
        self.assertEqual(reassembler.assembled_bytes, 8)
        self.expectData(reassembler, b"abcdefgh")
        self.assertEqual(reassembler._eof, False)
        data = b"abcdefgh"
        for i in range(1000):
            start_i = random.randint(0, 8)
            start = start_i
            end_i = random.randint(start_i, 8)
            end = end_i
            reassembler.data_received(start_i, data[start:end], False)
            self.assertEqual(reassembler.assembled_bytes, 8)
            self.expectData(reassembler, b"")
            self.assertEqual(reassembler._eof, False)

    def test_many_refill_before_close(self):
        MAX_SEG_LEN = 2048
        NSEGS = 128
        NREPS = 32

        for _ in range(NREPS):
            reassembler = StreamReassembler(MAX_SEG_LEN * NSEGS)
            seq_size = []
            offset = 0
            for i in range(NSEGS):
                size = 1 + random.randint(0, MAX_SEG_LEN - 1)
                seq_size.append((offset, size))
                offset += size
            random.shuffle(seq_size)

            d = bytearray(offset)
            for i in range(offset):
                d[i] = random.randint(0, 255)

            for off, sz in seq_size:
                reassembler.data_received(off, d[off : off + sz], off + sz == offset)

            result = reassembler.stream_out.read(reassembler.stream_out.size)
            self.assertEqual(reassembler.assembled_bytes, offset)
            self.assertEqual(result, d)

    def test_many_insert_EOF_into_a_hole(self):
        NREPS = 32
        for _ in range(NREPS):
            reassembler = StreamReassembler(65000)

            size = 1024
            d = bytearray(size)
            for i in range(size):
                d[i] = random.randint(0, 255)
            reassembler.data_received(0, d, False)
            reassembler.data_received(size + 10, d[10:], False)

            res1 = reassembler.stream_out.read(reassembler.stream_out.size)
            self.assertEqual(reassembler.assembled_bytes, size)
            self.assertEqual(res1, d)

            reassembler.data_received(size, d[:7], False)
            reassembler.data_received(size + 7, d[7:8], True)
            self.expectData(reassembler, d[:8])
            self.assertEqual(reassembler.assembled_bytes, size + 8)

    def test_many_insert_EOF_over_pre_queue(self):
        NREPS = 32
        for _ in range(NREPS):
            reassembler = StreamReassembler(65000)

            size = 1024
            d = bytearray(size)
            for i in range(size):
                d[i] = random.randint(0, 255)
            reassembler.data_received(0, d, False)
            reassembler.data_received(size + 10, d[10:], False)

            res1 = reassembler.stream_out.read(reassembler.stream_out.size)
            self.assertEqual(reassembler.assembled_bytes, size)
            self.assertEqual(res1, d)

            reassembler.data_received(size, d[0:15], True)
            res2 = reassembler.stream_out.read(reassembler.stream_out.size)
            self.assertEqual(
                reassembler.assembled_bytes == 2 * size
                or reassembler.assembled_bytes == size + 10,
                True,
            )
            self.assertEqual(res2, d)

    def test_seq(self):
        reassembler = StreamReassembler(65000)
        ss = ""
        for i in range(100):
            self.assertEqual(reassembler.assembled_bytes, 4 * i)
            self.checkBuffer(reassembler, 4 * i, b"abcd", False, [])
            self.assertEqual(reassembler.finished, False)
            ss += b"abcd".decode()
        self.expectData(reassembler, ss.encode())

    def test_win(self):
        MAX_SEG_LEN = 2048
        NSEGS = 128
        NREPS = 32
        # overlapping segments
        for _ in range(NREPS):
            reassembler = StreamReassembler(MAX_SEG_LEN * NSEGS)
            seq_size = []
            offset = 0
            for i in range(NSEGS):
                size = 1 + (random.randint(0, MAX_SEG_LEN - 1))
                offs = min(offset, 1 + (random.randint(0, 1023)))
                seq_size.append((offset - offs, size + offs))
                offset += size
            random.shuffle(seq_size)

            d = bytearray(offset)
            for i in range(offset):
                d[i] = random.randint(0, 255)

            for off, sz in seq_size:
                reassembler.data_received(off, d[off : off + sz], off + sz == offset)

            result = reassembler.stream_out.read(reassembler.stream_out.size)
            self.assertEqual(reassembler.assembled_bytes, offset)
            self.assertEqual(result, d)


if __name__ == '__main__':
    unittest.main()
