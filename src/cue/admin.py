from __future__ import annotations

import argparse

from cue.config import get_settings
from cue.db import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(prog="cue-admin")
    parser.add_argument("command", choices=["migrate"])
    args = parser.parse_args()
    if args.command == "migrate":
        run_migrations(get_settings())
