import argparse
from pathlib import Path
import signal
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--entered-file", type=Path, required=True)
    parser.add_argument("--terminating-file", type=Path)
    parser.add_argument("--exited-file", type=Path)
    parser.add_argument("--shutdown-delay", type=float, default=0.0)
    parser.add_argument("--run-seconds", type=float, default=0.0)
    args = parser.parse_args()

    args.pid_file.write_text(str(__import__("os").getpid()))
    args.entered_file.write_text(str(time.monotonic()))

    def stop(signum, frame) -> None:
        if args.terminating_file is not None:
            args.terminating_file.write_text(str(time.monotonic()))
        time.sleep(args.shutdown_delay)
        if args.exited_file is not None:
            args.exited_file.write_text(str(time.monotonic()))
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    time.sleep(args.run_seconds)
    if args.exited_file is not None:
        args.exited_file.write_text(str(time.monotonic()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
