import unittest
import random

from utils import wrap, unwrap, uint32, uint64

UINT32_MAX = (1 << 32) - 1
INT32_MAX = (1 << 31) - 1


class TestWrap(unittest.TestCase):
    def test_wrap(self):
        self.assertEqual(wrap(3 * (1 << 32), 0), 0)
        self.assertEqual(wrap(3 * (1 << 32) + 17, 15), 32)
        self.assertEqual(wrap(7 * (1 << 32) - 2, 15), 13)

    def test_unwrap(self):
        # unwrap(n: uint32, isn: uint32, checkpoint: uint64)
        # Unwrap the first byte after ISN
        self.assertEqual(unwrap(1, 0, 0), 1)
        # Unwrap the first byte after the first wrap
        self.assertEqual(unwrap(1, 0, UINT32_MAX - 1), (1 << 32) + 1)
        # Unwrap the last byte before the third wrap
        self.assertEqual(unwrap(UINT32_MAX - 1, 0, 3 * (1 << 32)), 3 * (1 << 32) - 2)
        # Unwrap the 10th from last byte before the third wrap
        self.assertEqual(unwrap(UINT32_MAX - 10, 0, 3 * (1 << 32)), 3 * (1 << 32) - 11)
        # Non-zero ISN
        self.assertEqual(unwrap(UINT32_MAX, 10, 3 * (1 << 32)), 3 * (1 << 32) - 11)
        # Big unwrap
        self.assertEqual(unwrap(UINT32_MAX, 0, 0), UINT32_MAX)
        # Unwrap a non-zero ISN
        self.assertEqual(unwrap(16, 16, 0), 0)

        # Big unwrap with non-zero ISN
        self.assertEqual(unwrap(15, 16, 0), UINT32_MAX)
        # Big unwrap with non-zero ISN
        self.assertEqual(unwrap(0, INT32_MAX, 0), INT32_MAX + 2)
        # Barely big unwrap with non-zero ISN
        self.assertEqual(unwrap(UINT32_MAX, INT32_MAX, 0), (1 << 31))
        # Nearly big unwrap with non-zero ISN
        self.assertEqual(unwrap(UINT32_MAX, 1 << 31, 0), UINT32_MAX >> 1)

    def _check_roundtrip(self, isn: uint32, value: uint64, checkpoint: uint64):
        self.assertEqual(unwrap(wrap(value, isn), isn, checkpoint), value)

    def test_roundtrip(self):
        greatest_offset = (1 << 31) - 1
        for i in range(100000):
            isn = random.randint(0, UINT32_MAX)
            ckp = random.randint(0, (1 << 63))
            offset = random.randint(0, greatest_offset)

            self._check_roundtrip(isn, ckp, ckp)
            self._check_roundtrip(isn, ckp + 1, ckp)
            self._check_roundtrip(isn, ckp - 1, ckp)
            self._check_roundtrip(isn, ckp + offset, ckp)
            self._check_roundtrip(isn, ckp - offset, ckp)
            self._check_roundtrip(isn, ckp + greatest_offset, ckp)
            self._check_roundtrip(isn, ckp - greatest_offset, ckp)


if __name__ == '__main__':
    unittest.main()
