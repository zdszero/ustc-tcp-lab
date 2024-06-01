import unittest
from stream_reassembler import StreamReassembler


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


if __name__ == '__main__':
    unittest.main()
