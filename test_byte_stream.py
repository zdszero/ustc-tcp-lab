import unittest
from byte_stream import ByteStream


class TestByteStream(unittest.TestCase):
    def test_capacity(self):
        bs = ByteStream(2)
        bs.write(b'cat')
        self.assertEqual(bs.bytes_written, 2)
        self.assertFalse(bs.input_ended)
        self.assertFalse(bs.empty)
        self.assertFalse(bs.eof)
        self.assertEqual(bs.bytes_read, 0)
        self.assertEqual(bs.bytes_written, 2)
        self.assertEqual(bs.remaining_capacity, 0)
        self.assertEqual(bs.size, 2)
        self.assertEqual(bs.peek_output(2), b'ca')

        self.assertEqual(bs.write(b't'), 0)

        self.assertFalse(bs.input_ended)
        self.assertFalse(bs.empty)
        self.assertFalse(bs.eof)
        self.assertEqual(bs.bytes_read, 0)
        self.assertEqual(bs.bytes_written, 2)
        self.assertEqual(bs.remaining_capacity, 0)
        self.assertEqual(bs.size, 2)
        self.assertEqual(bs.peek_output(2), b'ca')

    def test_overwrite(self):
        bs = ByteStream(10)
        self.assertEqual(bs.write(b'012'), 3)
        self.assertEqual(bs.size, 3)
        self.assertEqual(bs.write(b'34567890123'), 7)
        self.assertEqual(bs.size, bs.capacity)
        self.assertEqual(bs.read(5), b'01234')
        self.assertEqual(bs.remaining_capacity, 5)
        self.assertEqual(bs.size, 5)
        self.assertEqual(bs.peek_output(3), b'567')
        self.assertEqual(bs.size, 5)
        self.assertEqual(bs.read(20), b'')
        self.assertTrue(bs.error)


if __name__ == '__main__':
    unittest.main()
