import unittest
import select
import random
from math import ceil
from typing import Optional
import socket
import os
from config import TcpConfig
from tcp_connection import TcpConnection
from tcp_segment import TCP_HEADER_LENGTH, TcpHeader, TcpSegment
from utils import UINT32_MAX, uint32_plus
from test_sender import SenderTestBase
from tcp_state import TcpState

class FsmTestBase(SenderTestBase):
    def setUp(self):
        self.r_sock, self.w_sock = socket.socketpair()
        self.conn = None

    def canRead(self) -> bool:
        readable, _, _ = select.select([self.r_sock], [], [], 0)
        return len(readable) > 0
    
    def canRead_Expect(self,conn:TcpConnection)->bool:
        if len(conn.segments_out) > 0:
            return True
        return False

    def writeSegments(self, conn: TcpConnection):
        for seg in conn.segments_out:
            self.w_sock.send(seg.serialize())
        conn.segments_out.clear()

    def readNoSegment(
        self
    ):
        self.assertTrue(not self.canRead())

    def readSegment(
        self,
        payload_size: int = 0,
        syn: Optional[bool] = None,
        ack: Optional[bool] = None,
        fin: Optional[bool] = None,
        seqno: Optional[int] = None,
        ackno: Optional[int] = None,
        win: Optional[int] = None,
        payload: Optional[bytes] = None
    ) -> TcpSegment:
        self.assertTrue(self.canRead())
        data = self.r_sock.recv(payload_size + TCP_HEADER_LENGTH)
        seg = TcpSegment.deserialize(data)
        assert seg
        if syn is not None:
            self.assertEqual(seg.header.syn, syn)
        if ack is not None:
            self.assertEqual(seg.header.ack, ack)
        if fin is not None:
            self.assertEqual(seg.header.fin, fin)
        if seqno is not None:
            self.assertEqual(seg.header.seqno, seqno)
        if ackno is not None:
            self.assertEqual(seg.header.ackno, ackno)
        if win is not None:
            self.assertEqual(seg.header.win, win)
        if payload_size is not None:
            self.assertEqual(len(seg.payload), payload_size)
        if payload is not None:
            self.assertEqual(seg.payload, payload)
        return seg

class FsmTest(FsmTestBase):
    def test_loopback(self):
        capacity = 65000
        for _ in range(64):
            offset = random.randint(capacity, UINT32_MAX)
            conn = self.new_eastablished_connection(65000, offset-1, offset-1)
            conn.segment_received(TcpSegment(
                TcpHeader(ack=True, seqno=offset, ackno=offset, win=capacity)))
            # data = random.randbytes(capacity)
            data = os.urandom(capacity)
            recv_data = b''

            sendoff = 0
            while sendoff < capacity:
                len = min(capacity - sendoff, random.randint(0, 8191))
                if len == 0:
                    continue
                conn.write(data[sendoff:sendoff+len])
                conn.tick(1)
                self.writeSegments(conn)
                self.assertEqual(conn.bytes_in_flight, len)
                self.assertTrue(self.canRead())
                
                n_segents = ceil(len / TcpConfig.MAX_PAYLOAD_SIZE)
                bytes_remaining = len

                # transfer the data segment
                for _ in range(n_segents):
                    expected_size = min(bytes_remaining, TcpConfig.MAX_PAYLOAD_SIZE)
                    seg = self.readSegment(payload_size=expected_size)
                    self.assertIsNotNone(seg)
                    assert seg
                    bytes_remaining -= expected_size
                    conn.segment_received(seg)
                    conn.tick(1)
                    recv_data += seg.payload

                self.writeSegments(conn)

                # transfer the bare ack segment
                for _ in range(n_segents):
                    seg = self.readSegment(payload_size=0, ack=True)
                    self.assertIsNotNone(seg)
                    assert seg
                    conn.segment_received(seg)
                    conn.tick(1)

                self.writeSegments(conn)
                self.readNoSegment()
                self.assertEqual(conn.bytes_in_flight, 0)

                sendoff += len

            self.assertEqual(data, recv_data)

    def test_reorder_1(self):
        # non-overlapping out-of-order segments
        capacity = 65000
        for _ in range(1):
            isn1 = random.randint(0, UINT32_MAX)
            isn2 = random.randint(0, UINT32_MAX)
            conn = self.new_eastablished_connection(capacity, isn1, isn2)
            seq_size = []
            sendoff = 0
            while sendoff < capacity:
                size = min(
                    capacity - sendoff,
                    random.randint(0, TcpConfig.MAX_PAYLOAD_SIZE - 1) + 1,
                )
                seq_size.append((sendoff, size))
                sendoff += size
            random.shuffle(seq_size)
            # d = random.randbytes(capacity)
            d = os.urandom(capacity)
            min_expected_ackno = uint32_plus(isn2, 1)
            max_expected_ackno = uint32_plus(isn2, 1)
            for off, sz in seq_size:
                conn.segment_received(
                    TcpSegment(
                        TcpHeader(
                            ack=True,
                            seqno=uint32_plus(isn2, 1 + off),
                            ackno=uint32_plus(isn1, 1),
                            win=capacity,
                        ),
                        d[off : off + sz],
                    )
                )
                if uint32_plus(off, 1 + isn2) == min_expected_ackno:
                    min_expected_ackno = uint32_plus(min_expected_ackno, sz)
                max_expected_ackno = uint32_plus(max_expected_ackno, sz)

                self.writeSegments(conn)
                recv_seg = self.readSegment(ack=True)
                self.readNoSegment()
                self.assertTrue(min_expected_ackno <= recv_seg.header.ackno <= max_expected_ackno)
            conn.tick(1)
            self.assertEqual(conn.read(len(d)), d)

    def test_reorder_2(self):
        # overlapping out-of-order segments
        capacity = 65000
        for _ in range(32):
            isn1 = random.randint(0, UINT32_MAX)
            isn2 = random.randint(0, UINT32_MAX)
            conn = self.new_eastablished_connection(capacity, isn1, isn2)

            seq_size = []
            sendoff = 0
            while sendoff < capacity:
                size = min(
                    capacity - sendoff,
                    random.randint(0, TcpConfig.MAX_PAYLOAD_SIZE - 1) + 1,
                )
                rem = TcpConfig.MAX_PAYLOAD_SIZE - size
                offs = 0
                if rem == 0:
                    offs = 0
                elif rem == 1:
                    offs = min(1, sendoff)
                else:
                    offs = min(min(sendoff, rem), 1 + (random.randint(0, rem - 1)))
                self.assertLessEqual(size + offs, TcpConfig.MAX_PAYLOAD_SIZE)
                seq_size.append((sendoff - offs, size + offs))
                sendoff += size
            self.assertLessEqual(sendoff, capacity)
            random.shuffle(seq_size)
            # d = random.randbytes(capacity)
            d = os.urandom(capacity)
            min_expected_ackno = uint32_plus(isn2, 1)
            max_expected_ackno = uint32_plus(isn2, 1)
            for off, sz in seq_size:
                conn.segment_received(
                    TcpSegment(
                        TcpHeader(
                            ack=True,
                            seqno=uint32_plus(isn2, 1 + off),
                            ackno=uint32_plus(isn1, 1),
                            win=capacity,
                        ),
                        d[off : off + sz],
                    )
                )
                if (
                    uint32_plus(off, 1 + isn2) <= min_expected_ackno
                    and uint32_plus(off, 1 + isn2) > min_expected_ackno
                ):
                    min_expected_ackno = uint32_plus(isn2, 1 + off + size)
                max_expected_ackno = uint32_plus(max_expected_ackno, sz)

                self.writeSegments(conn)
                recv_seg = self.readSegment(ack=True)
                self.readNoSegment()
                self.assertTrue(min_expected_ackno <= recv_seg.header.ackno <= max_expected_ackno)
            conn.tick(1)
            self.assertEqual(conn.read(len(d)), d)

    def test_retx(self):
        capacity = 65000
        tx_ackno= random.randint(0, UINT32_MAX)
        conn= self.new_eastablished_connection(capacity, tx_ackno-1,tx_ackno-1)
        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno-1,ackno=tx_ackno,win=capacity)))
        data=b'asdf'
        conn.write(data)
        conn.tick(1)
        self.expectSegment(conn,payload_size=len(data),payload=data)
        self.expectNoSegment(conn)
        
        conn.tick(TcpConfig.rt_timeout-2)
        self.expectNoSegment(conn)

        conn.tick(2)
        self.expectSegment(conn,payload_size=len(data),payload=data)
        self.expectNoSegment(conn)

        conn.tick(10*TcpConfig.rt_timeout+100)
        self.expectSegment(conn,payload_size=len(data),payload=data)
        self.expectNoSegment(conn)  

        for i in range(2,TcpConfig.MAX_RETX_ATTEMPTS):
            conn.tick((TcpConfig.rt_timeout << i)-i)  # exponentially increasing delay length
            self.expectNoSegment(conn)
            conn.tick(i)
            self.expectSegment(conn,payload_size=len(data),payload=data)
            self.expectNoSegment(conn)

        self.assertEqual(conn.state,TcpState.ESTABLISHED)
        # self.assertEqual(conn.active,True)
        conn.tick(1+(TcpConfig.rt_timeout << TcpConfig.MAX_RETX_ATTEMPTS))
        self.assertEqual(conn.active,False)
        self.expectSegment(conn,rst=True)

    
    def test_retx_win_1(self):
        # multiple segments with intervening ack
        capacity = 65000
        tx_ackno= random.randint(0, UINT32_MAX)
        conn= self.new_eastablished_connection(capacity, tx_ackno-1,tx_ackno-1)
        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno-1,ackno=tx_ackno,win=capacity)))
        d1=b'asdf'
        d2=b'qwer'
        conn.write(d1)
        conn.tick(1+20)
        conn.write(d2)
        conn.tick(1)

        self.writeSegments(conn)
        self.canRead()
        self.readSegment(payload_size=len(d1),payload=d1)
        self.readSegment(payload_size=len(d2),payload=d2)     

        conn.tick(TcpConfig.rt_timeout-23)
        self.expectNoSegment(conn)

        conn.tick(4)
        self.expectSegment(conn,payload_size=len(d1),payload=d1)
        self.expectNoSegment(conn)

        conn.tick(2*TcpConfig.rt_timeout-2)
        self.expectNoSegment(conn)  

        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno,ackno=tx_ackno+len(d1),win=capacity)))
        conn.tick(TcpConfig.rt_timeout-2)
        self.expectNoSegment(conn)
        conn.tick(3)
        self.expectSegment(conn,payload_size=len(d2),payload=d2)
        self.expectNoSegment(conn)


    def test_retx_win_2(self):
        # multiple segments without intervening ack
        capacity = 65000
        tx_ackno= random.randint(0, UINT32_MAX)
        conn= self.new_eastablished_connection(capacity, tx_ackno-1,tx_ackno-1)
        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno-1,ackno=tx_ackno,win=capacity)))
        d1=b'asdf'
        d2=b'qwer'
        conn.write(d1)
        conn.tick(1+20)
        conn.write(d2)
        conn.tick(1)

        self.writeSegments(conn)
        self.canRead()
        self.readSegment(payload_size=len(d1),payload=d1)
        self.readSegment(payload_size=len(d2),payload=d2)     

        conn.tick(TcpConfig.rt_timeout-23)
        self.expectNoSegment(conn)

        conn.tick(4)
        self.expectSegment(conn,payload_size=len(d1),payload=d1)
        self.expectNoSegment(conn)

        conn.tick(2*TcpConfig.rt_timeout-2)
        self.expectNoSegment(conn)  

        conn.tick(3)
        self.expectSegment(conn,payload_size=len(d1),payload=d1)
        self.expectNoSegment(conn)

    def test_retx_win_3(self):
        # check that ACK of new data resets exponential backoff and restarts timer
        def backoff_test(num_backoffs: int):
            capacity = 65000
            tx_ackno= random.randint(0, UINT32_MAX)
            conn= self.new_eastablished_connection(capacity, tx_ackno-1,tx_ackno-1)
            conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno-1,ackno=tx_ackno,win=capacity)))
            d1=b'asdf'
            d2=b'qwer'
            conn.write(d1)
            conn.tick(1+20)
            conn.write(d2)
            conn.tick(1)

            self.writeSegments(conn)
            self.canRead()
            self.readSegment(payload_size=len(d1),payload=d1)
            self.readSegment(payload_size=len(d2),payload=d2) 
            conn.tick(TcpConfig.rt_timeout-23)
            self.expectNoSegment(conn)

            conn.tick(4)
            self.expectSegment(conn,payload_size=len(d1),payload=d1)
            self.expectNoSegment(conn)

            for i in range(1,num_backoffs):
                conn.tick((TcpConfig.rt_timeout << i)-i)  # exponentially increasing delay length
                self.expectNoSegment(conn)
                conn.tick(i)
                self.expectSegment(conn,payload_size=len(d1),payload=d1)
            
            # make sure RTO timer restarts on successful ACK
            conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=tx_ackno,ackno=tx_ackno+len(d1),win=capacity)))
            conn.tick(TcpConfig.rt_timeout-2)
            self.expectNoSegment(conn)
            conn.tick(3)
            self.expectSegment(conn,payload_size=len(d2),payload=d2)
            self.expectNoSegment(conn)
        
        for i in range(TcpConfig.MAX_RETX_ATTEMPTS):
            backoff_test(i)

    
    def test_winsize(self):
        MIN_SWIN=2048
        MAX_SWIN=34816
        MIN_SWIN_MUL=2
        MAX_SWIN_MUL=6
        cfg= TcpConfig()
        cfg.send_capacity=MAX_SWIN*MAX_SWIN_MUL

        # listen -> established -> check advertised winsize -> check sent bytes before ACK
        for i in range(1):
            cfg.recv_capacity = 2048+random.randint(0, 32767)
            seq_base= random.randint(0, UINT32_MAX)
            
            # connect
            conn=TcpConnection(cfg)
            conn.set_listening()
            conn.segment_received(TcpSegment(TcpHeader(syn=True,seqno=seq_base)))
            self.writeSegments(conn)
            seg=self.readSegment(ack=True,syn=True ,ackno=seq_base+1,win=cfg.recv_capacity)
            seg_hdr=seg.header
            ack_base=seg_hdr.seqno 

            # ack
            swin=MIN_SWIN+random.randint(0,MAX_SWIN-MIN_SWIN-1)
            conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=seq_base+1,ackno=ack_base+1,win=swin))) # adjust send window

            self.expectNoSegment(conn)
            self.assertEqual(conn.state,TcpState.ESTABLISHED)

            # write swin_mul * swin, make sure swin gets sent
            swin_mul=MIN_SWIN_MUL+random.randint(0,MAX_SWIN_MUL-MIN_SWIN_MUL-1)
            # d=random.randbytes(swin_mul*swin) python>=3.9
            d = os.urandom(swin_mul*swin)
            conn.write(d)
            conn.tick(1)
            # self.expectSegment(conn,no_flags=True,seqno=ack_base+1,win=cfg.recv_capacity) # check that swin is sent
            # print('send_cap:',conn._send_capacity,'bytes_in_flight:',conn.bytes_in_flight,'swin:',swin,'recv_cap:',recv_capacity,'swin*swin_mul:',swin_mul*swin)
            d_out=bytearray(swin_mul*swin)
            bytes_total=0
            while bytes_total < swin_mul*swin :
                bytes_read=0
                while self.canRead_Expect(conn):
                    seg2=self.expectSegment(conn,seqno=uint32_plus(ack_base,1+bytes_total+bytes_read),win=cfg.recv_capacity)
                    seg2_hdr=seg2.header
                    bytes_read+=len(seg2.payload)
                    seg2_first=seg2_hdr.seqno-ack_base-1
                    d_out[seg2_first:seg2_first+len(seg2.payload)] = seg2.payload
                self.assertFalse(bytes_read+TcpConfig.MAX_PAYLOAD_SIZE < swin)
                self.assertEqual(conn.bytes_in_flight,bytes_read)
                bytes_total+=bytes_read
                conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=seq_base+1,ackno=ack_base+1+bytes_total,win=swin)))
                conn.tick(1)
            self.assertEqual(conn.bytes_in_flight,0)
            self.assertEqual(d,d_out)

    def test_listen(self):
        # START -> LISTEN -> data without ACK or SYN (dropped) -> SYN -> SYN/ACK -> ACK
        conn=TcpConnection(TcpConfig())
        # tell the FSM to connect, make sure we get a SYN
        conn.set_listening()
        conn.tick(1)
        conn.segment_received(TcpSegment(TcpHeader(seqno=0)))
        conn.segment_received(TcpSegment(TcpHeader(fin=True)))
        conn.tick(1)
        self.assertEqual(conn.state,TcpState.LISTEN)
        self.expectNoSegment(conn)
        # print(conn.next_seqno)

        conn.segment_received(TcpSegment(TcpHeader(syn=True,seqno=1)))
        conn.tick(1)

        seg=self.expectSegment(conn,syn=True,ack=True,ackno=2)
        self.assertEqual(conn.state,TcpState.SYN_RECEIVED)

        # wrong seqno! should get ACK back but not transition    we make it: wrong seqno is dropped and no ans
        syn_no=seg.header.seqno
        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=1,ackno=syn_no+1)))
        conn.tick(1)
        # self.expectSegment(conn,ack=True,ackno=2,seqno=syn_no+1)
        self.assertEqual(conn.state,TcpState.SYN_RECEIVED)

        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=conn._recv_capacity+1,ackno=syn_no+1)))
        conn.tick(1)
        # self.expectSegment(conn,ack=True,ackno=2,seqno=syn_no+1)
        self.assertEqual(conn.state,TcpState.SYN_RECEIVED)

        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=2,ackno=syn_no+1)))
        conn.tick(1)
        self.expectNoSegment(conn)
        self.assertEqual(conn.state,TcpState.ESTABLISHED)

    def test_connect(self):
        # START -> SYN_SENT -> ACK (ignored) -> SYN (ignored) -> SYN+ACK -> ESTABLISHED 
        conn=TcpConnection(TcpConfig())
        conn.connect()
        conn.tick(1)
        seg=self.expectSegment(conn,syn=True)
        self.assertEqual(conn.state,TcpState.SYN_SENT)
        conn.tick(conn._rto)
        self.expectSegment(conn,syn=True)
        
        # send ACK only (no SYN yet)
        conn.segment_received(TcpSegment(TcpHeader(ack=True,seqno=0,ackno=seg.header.seqno+1)))
        conn.tick(1)
        self.assertEqual(conn.state,TcpState.SYN_SENT)
 
        # send SYN onlu (no ACK yet)
        isn=random.randint(0,UINT32_MAX)
        conn.segment_received(TcpSegment(TcpHeader(syn=True,seqno=isn)))
        conn.tick(1)
        self.assertEqual(conn.state,TcpState.SYN_SENT)

        # send SYN+ACK
        conn.segment_received(TcpSegment(TcpHeader(syn=True,ack=True,seqno=isn,ackno=seg.header.seqno+1)))
        conn.tick(1)
        self.assertEqual(conn.state,TcpState.ESTABLISHED)

        self.expectSegment(conn,ack=True,ackno=isn+1)


    def test_active_close(self):
        cap = 1000
        sender_isn, receiver_isn = 10000, 20000
        # ESTABLISHED -> FIN_WAIT_1 -> FIN_WAIT_2 -> TIME_WAIT -> (time out) -> CLOSED
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10)))
        conn.shutdown_write()
        self.expectSegment(conn, fin=True, seqno=sender_isn+1)
        self.expectNoSegment(conn)
        self.assertEqual(conn.state, TcpState.FIN_WAIT_1)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+2)))
        self.assertEqual(conn.state, TcpState.FIN_WAIT_2)
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.tick(2*TcpConfig.MSL-1)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.tick(1)
        self.assertEqual(conn.state, TcpState.CLOSED)

        # ESTABLISHED -> FIN_WAIT_1 -> CLOSING -> TIME_WAIT -> (time out) -> CLOSED
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10))) 
        conn.shutdown_write()
        seg=self.expectSegment(conn, fin=True, seqno=sender_isn+1) # FIN_WAIT_1
        conn.segment_received(TcpSegment(TcpHeader(fin=True,seqno=receiver_isn+1)))
        self.assertEqual(conn.state, TcpState.CLOSING)   # CLOSING
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=seg.header.seqno+1)))
        self.expectNoSegment(conn)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)    # TIME_WAIT
        conn.tick(2*TcpConfig.MSL-1)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.tick(1)
        self.assertEqual(conn.state, TcpState.CLOSED)

        # ESTABLISHED -> FIN_WAIT_1 -> FIN_WAIT_2 -> TIME_WAIT -> FIN again -> (time out) -> CLOSED
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10)))
        conn.shutdown_write()
        self.expectSegment(conn, fin=True, seqno=sender_isn+1)
        self.expectNoSegment(conn)
        self.assertEqual(conn.state, TcpState.FIN_WAIT_1)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+2)))
        self.assertEqual(conn.state, TcpState.FIN_WAIT_2)
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.tick(2*TcpConfig.MSL-1)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)
        conn.tick(2*TcpConfig.MSL)
        self.assertEqual(conn.state, TcpState.CLOSED)

        # start in ESTABLISHED, send FIN, time out,send FIN again, get FIN, send ACK, get ACK, time out
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10)))
        conn.shutdown_write()
        self.expectSegment(conn, fin=True, seqno=sender_isn+1)
        self.expectNoSegment(conn)
        conn.tick(conn._rto-2)
        self.expectNoSegment(conn)
        conn.tick(2)
        self.expectSegment(conn, fin=True, seqno=sender_isn+1) # FIN again
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.assertEqual(conn.state, TcpState.CLOSING)   # CLOSING
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+2)))
        self.expectNoSegment(conn)
        self.assertEqual(conn.state, TcpState.TIME_WAIT)    # TIME_WAIT
        conn.tick(2*TcpConfig.MSL)
        self.assertEqual(conn.state, TcpState.CLOSED)

    def test_passive_close(self):
        cap = 1000
        sender_isn, receiver_isn = 10000, 20000
        # CLOSE_WAIT -> LAST_ACK -> (ack) -> CLOSED
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10)))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        self.assertEqual(conn.state, TcpState.CLOSE_WAIT)       #CLOSE_WAIT
        conn.shutdown_write()
        self.expectSegment(conn, fin=True, seqno=sender_isn+1)
        self.assertEqual(conn.state, TcpState.LAST_ACK)         #LAST_ACK
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+2)))
        self.assertEqual(conn.state, TcpState.CLOSED)           #CLOSED

        # CLOSE_WAIT -> LAST_ACK -> (time out) -> FIN -> (wrong ack) -> (ack) -> CLOSED
        conn = self.new_eastablished_connection(cap, sender_isn, receiver_isn)
        conn.segment_received(TcpSegment(TcpHeader(ack=True, seqno=receiver_isn+1, win=10)))
        self.assertEqual(conn.state, TcpState.ESTABLISHED)
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)
        self.assertEqual(conn.state, TcpState.CLOSE_WAIT)       #CLOSE_WAIT
        conn.segment_received(TcpSegment(TcpHeader(fin=True, seqno=receiver_isn+1)))
        self.expectSegment(conn, ack=True, ackno=receiver_isn+2)    # re FIN and ACK
        conn.shutdown_write()
        seg=self.expectSegment(conn, fin=True, seqno=sender_isn+1)
        self.assertEqual(conn.state, TcpState.LAST_ACK)         #LAST_ACK
        conn.tick(conn._rto-2)
        self.expectNoSegment(conn)
        self.assertEqual(conn.state, TcpState.LAST_ACK)         #LAST_ACK
        conn.tick(2)
        self.expectSegment(conn, fin=True, seqno=seg.header.seqno)  #FIN
        self.assertEqual(conn.state, TcpState.LAST_ACK)         #LAST_ACK
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+3))) #wrong ack
        self.assertEqual(conn.state, TcpState.LAST_ACK)         #LAST_ACK
        conn.segment_received(TcpSegment(TcpHeader(ack=True, ackno=sender_isn+2)))
        self.assertEqual(conn.state, TcpState.CLOSED)           #CLOSED

    def tearDown(self):
        self.r_sock.close()
        self.w_sock.close()


if __name__ == "__main__":
    unittest.main()
