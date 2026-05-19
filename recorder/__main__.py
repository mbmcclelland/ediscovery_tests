"""
Entrypoint: `python -m recorder [--tick N] [--org O] [--store PATH]`.

This is what the systemd unit's ExecStart points at. For CLI-friendly
invocation (start/stop/status) use `dr-load record …` instead.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from recorder.daemon import run


def main() -> None:
    p = argparse.ArgumentParser(description="dr-load recorder daemon")
    p.add_argument("--tick", type=int, default=10, help="tick interval in seconds")
    p.add_argument("--org", type=str, default=None, help="DR org to poll")
    p.add_argument("--store", type=Path, default=None, help="SQLite store path")
    args = p.parse_args()

    run(store_path=args.store, org=args.org, tick_sec=args.tick)


if __name__ == "__main__":
    main()
