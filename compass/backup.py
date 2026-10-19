"""Consistent SQLite online backup. Never overwrite an existing destination."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or not source.is_file():
        raise ValueError(
            "Source must be an existing database, distinct from destination"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects earlier backups, including races.
    with destination.open("xb"):
        pass
    try:
        with closing(
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        ) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity check failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="instance/compass.db")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(backup(args.database, args.output))
