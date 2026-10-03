"""Produce a consistent online SQLite snapshot, including profiles, sessions and avatars."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def backup(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise ValueError('Database does not exist')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30) as src, sqlite3.connect(temporary) as dst:
            os.chmod(temporary, 0o600)
            src.backup(dst)
            if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prefix', choices=['shadowtable', 'inkmind'], default='shadowtable')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    print(backup(args.source.resolve(), args.directory / (args.prefix + '-' + stamp + '.sqlite')))
