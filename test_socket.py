import socket
import threading
import unittest
from config import FdAdapterConfig
from libtypes import *
from event_loop import *
from tcp_segment import *
from utils import *
from fd_adapter import TcpOverIpv4OverTunAdapter
from tcp_socket import TcpSocket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect to remote tcp server to get local inet addr
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "Unable to get IP address"
    finally:
        s.close()
    return local_ip

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))  # 绑定到一个空闲的端口
    s.listen(1)  # 使套接字处于监听状态
    port = s.getsockname()[1]  # 获取分配的端口号
    s.close()  # 关闭套接字
    return port


# 自动选择 IP地址 和 可用端口
REAL_SOCK_IP = get_local_ip()
REAL_SOCK_PORT = find_free_port()


def tcp_echo_server():
    """
    echo server
    接收到什么数据，就返回什么数据
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # bind to local ip
    s.bind((REAL_SOCK_IP, REAL_SOCK_PORT))
    s.listen()
    print("Server is listening...")
    s.settimeout(2)  # Add timeout to prevent hanging forever
    try:
        conn, peer_addr = s.accept()
        print(f'Accepted connection from {peer_addr}')
        while True:
            data = conn.recv(1024)
            # 接收到 FIN 退出循环
            if not data:
                break
            conn.send(data)
        conn.close()
        print('tcp server closed')
    except socket.timeout:
        print("Server timed out waiting for a connection.")
    finally:
        s.close()

        print("Server socket closed.")


# TunAdapter 的配置，包含真实 tcp server 的地址和 pytcp client 的地址
testcfg = FdAdapterConfig(
    saddr='169.254.0.9',
    sport=30732,
    daddr=REAL_SOCK_IP,
    dport=REAL_SOCK_PORT
)


class TestTunAdapter(unittest.TestCase):
    """
    在调用测试函数 test_* 前需要使用命令 ./tun.sh start 0 创建一个 tun0 设备
    tcp_echo_server 函数中的真实 tcp 在当前机器的 IPv4 网段中（内网地址）
    TunAdapterTcp 运行在 tun0 的虚拟网络的网段中
    """
    def create_tun_adapter(self):
        adapter = TcpOverIpv4OverTunAdapter('tun0')
        adapter.config = testcfg
        adapter.listening = True
        return adapter

    # 测试能否与真实 tcp server 建立三次握手
    def three_hand_shake(self,
                         adapter: TcpOverIpv4OverTunAdapter,
                         isn: int):
        # Write SYN segment
        adapter.write(TcpSegment(
            TcpHeader(
                syn=True,
                win=10000,
                seqno=isn
            )
        ))
        print("SYN segment written.")

        # Read SYN-ACK segment
        seg = adapter.read()
        self.assertIsNotNone(seg)
        assert seg # pyright check
        self.assertTrue(seg.header.syn)
        self.assertTrue(seg.header.ack)
        self.assertEqual(seg.header.ackno, isn+1)
        print("SYN-ACK segment received.")
        peer_isn = seg.header.seqno

        # Write ACK segment
        next_seqno = uint32_plus(seg.header.seqno, 1)
        adapter.write(TcpSegment(
            TcpHeader(
                ack=True,
                win=10000,
                ackno=next_seqno,
                seqno=isn+1
            )
        ))
        print("ACK segment written.")
        return peer_isn


    # 主动关闭 tcp 连接
    def active_close(self,
                    adapter: TcpOverIpv4OverTunAdapter,
                    fin_seqno: int,
                    ackno: int):
        print('Send fin')
        adapter.write(TcpSegment(
            TcpHeader(
                fin=True,
                ack=True,
                ackno=ackno,
                seqno=fin_seqno,
                win=10000
            )
        ))
        seg = adapter.read()
        self.assertIsNotNone(seg)
        assert seg
        print('Receive fin ack')
        self.assertTrue(seg.header.ack)
        self.assertTrue(seg.header.fin)
        fin_ackno = seg.header.seqno+1
        adapter.write(
            TcpSegment(
                TcpHeader(
                    ack=True,
                    ackno=fin_ackno,
                    seqno=fin_seqno+1,
                    win=10000
                )
            )
        )

    # 发送数据并确认可以收到来自 tcp echo server 的相同数据
    def send_data(self,
                  adapter: TcpOverIpv4OverTunAdapter,
                  data: bytes,
                  seqno: int,
                  ackno: int):
        adapter.write(
            TcpSegment(
                TcpHeader(
                    ack=True,
                    seqno=seqno,
                    ackno=ackno,
                    win=10000
                ),
                payload=data
            )
        )
        seg = adapter.read()
        self.assertIsNotNone(seg)
        assert seg
        self.assertTrue(seg.header.ack)
        self.assertEqual(seg.header.seqno, ackno)
        # 如果 tcp_echo_server 并没有将 ACK 和 data 放在一起，需要多检验一次
        if len(seg.payload) == 0:
            seg = adapter.read()
            self.assertIsNotNone(seg)
            assert seg
            self.assertEqual(data, seg.payload)
        else:
            self.assertEqual(data, seg.payload)

    # 握手后马上挥手
    def test_connect_then_close(self):
        t = threading.Thread(target=tcp_echo_server)
        t.start()

        adapter = self.create_tun_adapter()
        peer_isn = self.three_hand_shake(adapter, 10000)
        self.active_close(adapter, 10001, peer_isn+1)

    # 握手、发送和接受数据、挥手
    def test_send_data(self):
        t = threading.Thread(target=tcp_echo_server)
        t.start()

        adapter = self.create_tun_adapter()
        peer_isn = self.three_hand_shake(adapter, 10000)
        self.send_data(adapter, b'abcde', 10001, peer_isn+1)
        self.send_data(adapter, b'0123456789', 10006, peer_isn+6)
        self.active_close(adapter, 10016, peer_isn+16)


class TestSocket(unittest.TestCase):
    def test_socket(self):
        t = threading.Thread(target=tcp_echo_server)
        t.start()
        s = TcpSocket(TcpOverIpv4OverTunAdapter("tun0"))
        s.connect(testcfg)
        request = "GET / HTTP/1.1\r\nHost: {}\r\n\r\n".format('192.168.31.128')
        s.write(request)
        t.join()


# class TestEventloop(unittest.TestCase):
#     def test_basic(self):
#         loop = EventLoop()
#         r, w = socket.socketpair()
#         loop.add_rule(r, READ_EVENT, lambda: print('readable'))
#         loop.add_rule(w, WRITE_EVENT, lambda: print('writable'))
#         w.send(b'12345')
#         loop.wait_next_event(100)
#         r.close()
#         w.close()


if __name__ == '__main__':
    unittest.main()
