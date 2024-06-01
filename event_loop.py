import selectors
from typing import Callable


class Rule:
    def __init__(
        self,
        direction: int,
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
        self.direction = direction
        self.callback = callback
        self.interest = interest
        self.cancel = cancel


class EventLoop:
    def __init__(self):
        self.selector = selectors.DefaultSelector()
        self.rules = {}

    def add_rule(
        self,
        fileobj,
        direction: int,
        callback: Callable,
        interest: Callable[[], bool] = lambda: True,
        cancel: Callable = lambda: None,
    ):
        self.rules[fileobj] = Rule(direction, callback, interest, cancel)
        self.selector.register(fileobj, direction)

    def wait_next_event(self, timeout_ms: int) -> bool:
        something_interested = False
        closed_fileobjs = []
        for fileobj, rule in self.rules.items():
            if fileobj.closed:
                closed_fileobjs.append(fileobj)
                continue
            if rule.interest and rule.interest():
                something_interested = True

        # unregister closed events
        for fileobj in closed_fileobjs:
            self.rules[fileobj].cancel()
            self.selector.unregister(fileobj)
            self.rules.pop(fileobj)

        # exit when not interested in any event
        if not something_interested:
            return False

        events = self.selector.select(timeout=timeout_ms / 1000)
        if not events:
            return False
        for key, mask in events:
            fileobj = key.fileobj
            interest = self.rules[fileobj].interest
            callback = self.rules[fileobj].callback
            if fileobj.closed:
                continue
            if interest and not interest():
                continue
            # trigger callback when interested and not closed
            callback()
        return True
