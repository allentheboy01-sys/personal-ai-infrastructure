import os
import socket
import threading

from jarvis.exec_proxy.main import SOCKET_PATH, _copy


def test_proxy_target_is_fixed_and_copy_does_not_buffer_short_frames() -> None:
    assert SOCKET_PATH == "/run/jarvis-exec.sock"
    source_read, source_write = os.pipe()
    left, right = socket.socketpair()
    worker = threading.Thread(target=_copy, args=(source_read, left.fileno()), kwargs={"shutdown": left})
    worker.start()
    os.write(source_write, b"short\n")
    assert right.recv(64) == b"short\n"
    os.close(source_write)
    worker.join(timeout=2)
    assert not worker.is_alive()
    os.close(source_read)
    left.close()
    right.close()
