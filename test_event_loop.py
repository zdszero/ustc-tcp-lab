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



class TestSocketPair(unittest.TestCase):
    def test_socket_pair(self):
        socket_pair = SocketPair()

        # 初始状态应为未关闭
        self.assertFalse(socket_pair.closed)

        # 关闭套接字
        socket_pair.close()

        # 状态应为已关闭
        self.assertTrue(socket_pair.closed)

        # 尝试使用已关闭的套接字应引发异常
        with self.assertRaises(ValueError):
            socket_pair.send(b"Hello")
        with self.assertRaises(ValueError):
            socket_pair.recv(1024)
        with self.assertRaises(ValueError):
            socket_pair.fileno()


class TestEventLoopWithSocketPair(unittest.TestCase):
    def setUp(self):
        self.loop = EventLoop()

    def test_read_event(self):
        socket_pair = SocketPair()

        def on_readable():
            data = socket_pair.recv(1024)
            self.assertEqual(data, b"Hello")
            socket_pair.close()

        self.loop.add_rule(socket_pair, READ_EVENT, on_readable)
        socket_pair.child_sock.sendall(b"Hello")
        self.loop.wait_next_event(1000)

    def test_write_event(self):
        socket_pair = SocketPair()

        def on_writable():
            socket_pair.send(b"Hello")
            data = socket_pair.child_sock.recv(1024)
            self.assertEqual(data, b"Hello")
            socket_pair.close()

        self.loop.add_rule(socket_pair, WRITE_EVENT, on_writable)
        self.loop.wait_next_event(1000)


if __name__ == "__main__":
    unittest.main()
