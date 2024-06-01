class TcpState:
    CLOSED = 0
    LISTEN = 1
    SYN_SENT = 2
    SYN_RECEIVED = 3
    ESTABLISHED = 4
    CLOSE_WAIT = 5
    LAST_ACK = 6
    FIN_WAIT_1 = 7
    FIN_WAIT_2 = 8
    CLOSING = 9
    TIME_WAIT = 10


state_descriptions = {
    TcpState.CLOSED: "CLOSED",
    TcpState.LISTEN: "LISTEN",
    TcpState.SYN_SENT: "SYN_SENT",
    TcpState.SYN_RECEIVED: "SYN_RECEIVED",
    TcpState.ESTABLISHED: "ESTABLISHED",
    TcpState.FIN_WAIT_1: "FIN_WAIT_1",
    TcpState.FIN_WAIT_2: "FIN_WAIT_2",
    TcpState.CLOSE_WAIT: "CLOSE_WAIT",
    TcpState.CLOSING: "CLOSING",
    TcpState.LAST_ACK: "LAST_ACK",
    TcpState.TIME_WAIT: "TIME_WAIT"
}


def describe_tcp_state(state):
    return state_descriptions.get(state, "Unknown state")
