import os
import socket
import select
from typing import Callable
import selectors
READ_EVENT = selectors.EVENT_READ
WRITE_EVENT = selectors.EVENT_WRITE

class Rule:
    def __init__(
        self,
        callback: Callable,
        interest: Callable[[], bool] = lambda: True,
        cancel: Callable = lambda: None,
    ):
        """
        direction: selectors.EVENT_READ | selectors.EVENT_WRITE
        callback: called when readabled or writable
        interest: the conditoin wheather or not fileobj should be selected
        cancel: called when fileobj is unregistered
        """
        self.callback = callback
        self.interest = interest
        self.cancel = cancel


class EventLoop:
    def __init__(self):
        self.read_rules = {}
        self.rlist = []
        self.write_rules = {}
        self.wlist = []

    def add_rule(
        self,
        fileobj,
        direction: int,
        callback: Callable,
        interest: Callable[[], bool] = lambda: True,
        cancel: Callable = lambda: None,
    ):
        if direction == READ_EVENT:
            self.read_rules[fileobj] = Rule(callback, interest, cancel)
            self.rlist.append(fileobj)
        elif direction == WRITE_EVENT:
            self.write_rules[fileobj] = Rule(callback, interest, cancel)
            self.wlist.append(fileobj)

    def _check_closed(self, fileobj) -> bool:
        if isinstance(fileobj, int):
            fd = fileobj
        else:
            try:
                fd = int(fileobj.fileno())
            except (AttributeError, TypeError, ValueError):
                raise ValueError("Invalid file object: "
                                 "{!r}".format(fileobj)) from None
        try:
            os.fstat(fd)
        except OSError:
            return True
        return False

    def wait_next_event(self, timeout_ms: int) -> bool:
        closed_fileobjs = []
        for fileobj in set(self.rlist + self.wlist):
            if self._check_closed(fileobj):
                closed_fileobjs.append(fileobj)

        something_interested = False
        for rule in self.read_rules.values():
            if rule.interest and rule.interest():
                something_interested = True
        for rule in self.write_rules.values():
            if rule.interest and rule.interest():
                something_interested = True

        # unregister closed events
        for fileobj in closed_fileobjs:
            if fileobj in self.write_rules:
                self.write_rules[fileobj].cancel()
                self.write_rules.pop(fileobj)
            if fileobj in self.read_rules:
                self.read_rules[fileobj].cancel()
                self.read_rules.pop(fileobj)

        # exit when not interested in any event
        if not something_interested:
            return False
        
        readable, writeable, _ = select.select(self.rlist, self.wlist, [], timeout_ms / 1000)

        something_interested = False
        if not readable and not writeable:
            return False
        for fileobj in readable:
            interest = self.read_rules[fileobj].interest
            callback = self.read_rules[fileobj].callback
            if self._check_closed(fileobj):
                continue
            if interest and not interest():
                continue
            something_interested=True
            callback()
        for fileobj in writeable:
            interest = self.write_rules[fileobj].interest
            callback = self.write_rules[fileobj].callback
            # print("interst:"+str(interest)+"interst():"+str(interest()))
            if self._check_closed(fileobj):
                continue
            if interest and not interest():
                continue
            something_interested=True
            callback()

        # print("something_interested :"+str(something_interested))
        # print("closed_fileobjs:"+",".join(closed_fileobjs))
        # print("rlist",end=':')
        # print(self.rlist)
        # print("wlist",end=':')
        # print(self.wlist)
        # print("readable:"+str(readable)+" writeable:"+str(writeable))

        if not something_interested:
            return False
        return True


class SocketPair:
    def __init__(self):
        self.parent_sock, self.child_sock = socket.socketpair()
        self._closed = False

    def fileno(self):
        if self._closed:
            raise ValueError("Socket is closed")
        return self.parent_sock.fileno()

    def recv(self, bufsize):
        if self._closed:
            raise ValueError("Socket is closed")
        return self.parent_sock.recv(bufsize)

    def send(self, data):
        if self._closed:
            raise ValueError("Socket is closed")
        return self.parent_sock.send(data)

    def close(self):
        if not self._closed:
            self.parent_sock.close()
            self.child_sock.close()
            self._closed = True

    @property
    def closed(self):
        return self._closed
