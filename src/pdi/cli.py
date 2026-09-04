"""Stable public command surface for PDI application composition."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from pdi.config import PDIConfigurationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdi",
        description="Personal Digital Infrastructure",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    sync = subcommands.add_parser(
        "sync",
        help="Synchronize configured Provider data into PDI.",
    )
    sync.add_argument(
        "--provider",
        choices=("nextcloud", "immich", "gmail"),
        help=(
            "Synchronize one Provider. Without this option, configured "
            "Nextcloud and Immich Providers are synchronized; Gmail remains "
            "explicit-only."
        ),
    )
    sync.add_argument(
        "--operation",
        choices=("full", "incremental", "bootstrap", "recover"),
        help="Provider sync operation; defaults to full.",
    )

    subcommands.add_parser(
        "mcp",
        help="Run the read-only PDI MCP server over stdio.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (
        args.command == "sync"
        and args.operation not in {None, "full"}
        and args.provider not in {"nextcloud", "immich"}
    ):
        parser.error(
            "non-full sync operations require an explicit "
            "Nextcloud or Immich provider"
        )
    try:
        if args.command == "sync":
            from pdi.main import main as sync_main

            sync_argv = []
            if args.provider is not None:
                sync_argv.extend(("--provider", args.provider))
            if args.operation is not None:
                sync_argv.extend(("--operation", args.operation))
            sync_main(sync_argv)
        else:
            from pdi_mcp.bootstrap import main as mcp_main

            mcp_main()
    except PDIConfigurationError as error:
        print(f"pdi: error: {error}", file=sys.stderr)
        return 2
    return 0
