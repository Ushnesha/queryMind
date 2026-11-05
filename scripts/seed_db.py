"""Create the small deterministic demo database explicitly, never on import."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3


def seed_database(path: str | Path) -> Path:
    """Create a new demo database; refuse to overwrite any existing file."""
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive file creation avoids overwriting a user's existing database.
    with destination.open("xb"):
        pass
    connection = sqlite3.connect(destination)
    try:
        with connection:
            connection.executescript(
                "CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT);"
                "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, "
                "amount REAL NOT NULL, order_date TEXT NOT NULL, "
                "FOREIGN KEY (customer_id) REFERENCES customers(customer_id));"
            )
            connection.executemany(
                "INSERT INTO customers VALUES (?, ?, ?)",
                [(1, "Alice Chen", "alice@example.test"), (2, "Bob Smith", "bob@example.test"),
                 (3, "Carol Davis", "carol@example.test"), (4, "Devin Reed", "devin@example.test")],
            )
            connection.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                [(1, 1, 200.0, "2025-01-01"), (2, 1, 100.0, "2025-01-02"),
                 (3, 2, 100.0, "2025-01-03"), (4, 2, 75.0, "2025-01-04"),
                 (5, 3, 50.0, "2025-01-05"), (6, 3, 25.0, "2025-01-06")],
            )
    finally:
        connection.close()
    return destination


def main(argv: list[str] | None = None) -> int:
    """Seed the configured demo path, preserving any existing database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args(argv)
    if args.db is None:
        from src.config import load_settings

        args.db = load_settings().database.path
    try:
        path = seed_database(args.db)
    except FileExistsError:
        print(f"Database already exists at {args.db}; left unchanged.")
    else:
        print(f"Created demo database: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
