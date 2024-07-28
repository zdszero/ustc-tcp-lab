import unittest
import socket
from event_loop import *

class TestEventLoop(unittest.TestCase):
    def setUp(self):
        self.loop = EventLoop()

    def test_read_event(self):
        parent_sock, child_sock = socket.socketpair()

        def on_readable():
            data = parent_sock.recv(1024)
            self.assertEqual(data, b"Hello")
            parent_sock.close()
            child_sock.close()

        self.loop.add_rule(parent_sock, READ_EVENT, on_readable)
        child_sock.sendall(b"Hello")
        self.loop.wait_next_event(1000)

    def test_write_event(self):
        parent_sock, child_sock = socket.socketpair()

        def on_writable():
            parent_sock.sendall(b"Hello")
            data = child_sock.recv(1024)
            self.assertEqual(data, b"Hello")
            parent_sock.close()
            child_sock.close()

        self.loop.add_rule(parent_sock, WRITE_EVENT, on_writable)
        self.loop.wait_next_event(1000)

    def test_close_file_descriptor(self):
        parent_sock, child_sock = socket.socketpair()

        def on_readable():
            data = parent_sock.recv(1024)
            self.assertEqual(data, b"Hello")
            parent_sock.close()

        self.loop.add_rule(parent_sock, READ_EVENT, on_readable)
        child_sock.sendall(b"Hello")
        self.loop.wait_next_event(1000)

        # Try to read again after closing
        closed = False
        try:
            parent_sock.recv(1024)
        except OSError:
            closed = True

        self.assertTrue(closed)

    def test_timeout(self):
        parent_sock, child_sock = socket.socketpair()

        def on_readable():
            pass

        self.loop.add_rule(parent_sock, READ_EVENT, on_readable)
        result = self.loop.wait_next_event(1000)  # 1 second timeout
        self.assertFalse(result)

        parent_sock.close()
        child_sock.close()

if __name__ == "__main__":
    unittest.main()
