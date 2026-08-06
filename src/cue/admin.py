from __future__ import annotations

import argparse
from pathlib import Path

from cue.backups import create_daily_backup, restore_backup
from cue.config import get_settings
from cue.db import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(prog="cue-admin")
    parser.add_argument("command", choices=["migrate", "backup", "restore"])
    parser.add_argument("--source", type=Path, help="Source backup for restore")
    parser.add_argument("--destination", type=Path, help="New restore destination")
    args = parser.parse_args()
    if args.command == "migrate":
        run_migrations(get_settings())
    elif args.command == "backup":
        print(create_daily_backup(get_settings()))
    else:
        if args.source is None or args.destination is None:
            parser.error("restore requires --source and --destination")
        restore_backup(args.source, args.destination)
