from __future__ import annotations

import inspect
import time
from config import ENABLED_CHANNELS

STYLES = {
    "</>": "\33[0m",
    "<WARN>": "\33[1m\33[93m",
    "<CRIT>": "\33[41m",
    "<INFO>": "\33[1m",
    "<B>": "\33[1m",
    "<I>": "\33[3m",
    "<U>": "\33[4m",
    "<r>": "\33[31m",
    "<lr>": "\33[91m",
    "<g>": "\33[32m",
    "<lg>": "\33[92m",
    "<y>": "\33[33m",
    "<ly>": "\33[93m",
    "<b>": "\33[34m",
    "<lb>": "\33[94m",
    "<c>": "\33[36m",
    "<lc>": "\33[96m",
    "<v>": "\33[35m",
    "<lv>": "\33[95m",
}


START_TIME = time.time()


def log(channel: str, message: str, inspect_depth: int = 0):
    if not __debug__:
        return
    output = ''
    if channel in ENABLED_CHANNELS:
        if inspect_depth > 0:
            frame_info = inspect.stack()[inspect_depth]
            caller_class = frame_info.frame.f_locals["self"].__class__.__name__
            caller_method = frame_info.function
            caller_info = f"{caller_class}.{caller_method}"
            output = (
                f" <g>{(time.time() - START_TIME):07.02f}</> | "
                f"<b>{channel.upper():7}</> | <c>{caller_info}</> | "
                f"{message}"
            )
        else:
            output = (
                f" <g>{(time.time() - START_TIME):07.02f}</> | "
                f"<b>{channel.upper():7}</> | {message}"
            )
    else:
        return

    for key, value in STYLES.items():
        output = output.replace(key, value)

    print(output)
