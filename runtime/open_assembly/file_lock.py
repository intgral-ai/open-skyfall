import os
from contextlib import contextmanager

if os.name == "nt":
    import msvcrt
    import time

    def _acquire(stream):
        # Windows locks a byte range from the file position; append mode opens at the end.
        stream.seek(0)
        while True:
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except PermissionError:
                time.sleep(0.01)

    def _release(stream):
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire(stream):
        fcntl.flock(stream, fcntl.LOCK_EX)

    def _release(stream):
        fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def exclusive_lock(stream):
    """Hold a blocking interprocess lock on an open binary file."""
    _acquire(stream)
    try:
        yield
    finally:
        _release(stream)
