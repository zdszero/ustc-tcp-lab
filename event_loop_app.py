import sys
import selectors
import threading

# 假设上面的代码定义在 event_loop.py 模块中
from event_loop import EventLoop


def stdin_callback():
    """从stdin读取数据并将其转换为大写后输出到stdout"""
    print('callback called')
    data = sys.stdin.readline()
    print('read data', data.upper())
    if not data:  # EOF
        print("EOF reached, stdin unregistered and closed")


def main():
    global loop
    loop = EventLoop()

    # 注册stdin的读事件
    loop.add_rule(
        sys.stdin,
        selectors.EVENT_READ,
        callback=stdin_callback,
        cancel=lambda: print("stdin has been unregistered from the event loop")
    )

    def my_function(name):
        print(f"Hello, {name}! Function called after 2 seconds")
        sys.stdin.close()

# 创建一个 Timer 对象，设定 2 秒后调用 my_function 并传递参数
    timer = threading.Timer(2.0, my_function, args=("Alice",))

# 启动计时器
    timer.start()

    print("Type something and press enter (Ctrl+D to exit):")
    try:
        while loop.wait_next_event(1000):
            print('no events, waiting ...')
    except KeyboardInterrupt:
        print("Event loop stopped by user")


if __name__ == "__main__":
    main()
