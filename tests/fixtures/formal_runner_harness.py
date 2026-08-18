import argparse
from pathlib import Path
import sys

from pdi import operational


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("--lock-timeout", type=float, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--entered-file", type=Path, required=True)
    parser.add_argument("--terminating-file", type=Path)
    parser.add_argument("--exited-file", type=Path)
    parser.add_argument("--shutdown-delay", type=float, default=0.0)
    parser.add_argument("--run-seconds", type=float, default=0.0)
    args = parser.parse_args()

    command = [
        "-m",
        "tests.fixtures.controlled_pipeline",
        "--pid-file",
        str(args.pid_file),
        "--entered-file",
        str(args.entered_file),
        "--shutdown-delay",
        str(args.shutdown_delay),
        "--run-seconds",
        str(args.run_seconds),
    ]
    if args.terminating_file is not None:
        command.extend(("--terminating-file", str(args.terminating_file)))
    if args.exited_file is not None:
        command.extend(("--exited-file", str(args.exited_file)))
    operational.PIPELINE_COMMANDS["provider.nextcloud.sync"] = tuple(command)
    try:
        return operational.run_formal_pipeline(
            "provider.nextcloud.sync",
            lock_timeout=args.lock_timeout,
            lock_path=args.lock_path,
        )
    except operational.RunnerInterrupted as interruption:
        return 128 + interruption.signum
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
