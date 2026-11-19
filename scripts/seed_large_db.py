"""Create a large deterministic synthetic database for optimizer evaluation at scale."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import random
import sqlite3
import sys
from time import perf_counter
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 12, 31)
MAX_JOIN_DATE = date(2025, 6, 30)

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry", "Ivy", "Jack",
    "Katherine", "Liam", "Mia", "Noah", "Olivia", "Peter", "Quinn", "Rachel", "Sam", "Tara",
    "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zack", "Aaron", "Bella", "Caleb", "Diana",
    "Ethan", "Fiona", "George", "Hannah", "Ian", "Julia", "Kevin", "Laura", "Michael", "Nora",
    "Oscar", "Penelope", "Ryan", "Sophia", "Thomas", "Victoria", "William", "Zoe", "Adam", "Brooke",
    "Chloe", "Daniel", "Ella", "Felix", "Gina", "Harry", "Isabel", "James", "Kelly", "Luke",
    "Maya", "Nathan", "Paige", "Owen", "Ruby", "Sean", "Tessa", "Tyler", "Valerie", "Wyatt",
    "Amber", "Blake", "Clara", "Derek", "Elena", "Finn", "Gavin", "Hazel", "Isaac", "Jenna",
    "Kyle", "Lily", "Mason", "Naomi", "Patrick", "Rose", "Seth", "Tracy", "Vance", "Walter",
    "Adele", "Brian", "Cody", "Daisy", "Eric", "Faith", "Grant", "Holly", "Jesse", "Leah",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
    "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins", "Reyes",
    "Stewart", "Morris", "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper",
    "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes",
    "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long", "Ross", "Foster", "Jimenez",
]


@dataclass(frozen=True)
class GenerationSummary:
    """Summary metrics of the generated large database."""

    db_path: Path
    customers: int
    orders: int
    inactive_customers: int
    active_customers: int
    total_spending: float
    min_order_amount: float
    max_order_amount: float
    mean_order_amount: float
    file_size_bytes: int
    generation_time_s: float
    synthetic_join_dates: dict[int, date]


def _generate_customer_name(customer_id: int) -> tuple[str, str]:
    """Deterministically generate (name, email) for customer_id."""
    first = FIRST_NAMES[(customer_id - 1) % len(FIRST_NAMES)]
    last = LAST_NAMES[((customer_id - 1) // len(FIRST_NAMES)) % len(LAST_NAMES)]
    name = f"{first} {last}"
    email = f"{first.lower()}.{last.lower()}{customer_id}@example.test"
    return name, email


def seed_large_database(
    path: str | Path,
    *,
    customers: int = 10000,
    orders: int = 100000,
    seed: int = 42,
    overwrite: bool = False,
) -> GenerationSummary:
    """Create the large synthetic SQLite database deterministically.

    Preserves the stakeholder schema and index structure exactly.
    Customer join dates are internal metadata and are NOT added to the database.
    """
    if customers < 1:
        raise ValueError("customers must be >= 1")
    if orders < 0:
        raise ValueError("orders must be >= 0")

    started = perf_counter()
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        if not overwrite:
            raise FileExistsError(
                f"Database already exists at {destination}. Pass overwrite=True or --overwrite to replace it."
            )
        destination.unlink()

    with destination.open("xb"):
        pass

    rng = random.Random(seed)

    # 1. Generate customers and their synthetic internal join dates
    max_join_days = (MAX_JOIN_DATE - START_DATE).days
    customer_rows: list[tuple[int, str, str]] = []
    synthetic_join_dates: dict[int, date] = {}
    active_cids: list[int] = []
    active_weights: list[float] = []

    for cid in range(1, customers + 1):
        name, email = _generate_customer_name(cid)
        customer_rows.append((cid, name, email))
        join_days = rng.randint(0, max_join_days)
        join_date = START_DATE + timedelta(days=join_days)
        synthetic_join_dates[cid] = join_date

        # Activity tier target: ~15% inactive, ~55% occasional, ~22% regular, ~8% power
        tier_roll = rng.random()
        if tier_roll < 0.15:
            pass  # Inactive: 0 orders
        elif tier_roll < 0.70:
            active_cids.append(cid)
            active_weights.append(1.0)  # Occasional
        elif tier_roll < 0.92:
            active_cids.append(cid)
            active_weights.append(6.0)  # Regular
        else:
            active_cids.append(cid)
            active_weights.append(35.0)  # Power customer

    # Safety: if no active customers were chosen, activate the first customer
    if not active_cids and customers > 0:
        active_cids.append(1)
        active_weights.append(1.0)

    # 2. Generate exactly N orders using weighted customer selection
    selected_cids: list[int] = []
    if orders > 0:
        if orders >= len(active_cids):
            # Guarantee every active customer gets at least 1 order,
            # then distribute the remaining orders by activity weight.
            selected_cids.extend(active_cids)
            remaining_orders = orders - len(active_cids)
            if remaining_orders > 0:
                selected_cids.extend(
                    rng.choices(active_cids, weights=active_weights, k=remaining_orders)
                )
        else:
            # When orders < active customers, sample directly by weight
            selected_cids.extend(
                rng.choices(active_cids, weights=active_weights, k=orders)
            )

    raw_orders: list[tuple[int, float, str]] = []
    total_timeline_days = (END_DATE - START_DATE).days

    for cid in selected_cids:
        c_join_date = synthetic_join_dates[cid]
        max_order_days = (END_DATE - c_join_date).days
        if max_order_days > 0:
            order_days = rng.randint(0, max_order_days)
            order_date = c_join_date + timedelta(days=order_days)

            # Modest Q4 holiday boost: if not Nov/Dec, 15% probability to shift toward Nov/Dec of same year
            if order_date.month not in (11, 12) and rng.random() < 0.15:
                holiday_offset = (date(order_date.year, 11, 1) - c_join_date).days + rng.randint(0, 60)
                if 0 <= holiday_offset <= max_order_days:
                    order_date = c_join_date + timedelta(days=holiday_offset)
        else:
            order_date = c_join_date

        raw_amount = rng.lognormvariate(3.6, 0.75)
        amount = round(max(5.0, min(3500.0, raw_amount)), 2)
        raw_orders.append((cid, amount, order_date.isoformat()))

    # Sort orders chronologically to reflect a realistic append transaction log
    raw_orders.sort(key=lambda o: o[2])

    order_rows: list[tuple[int, int, float, str]] = [
        (order_id, cid, amt, dt)
        for order_id, (cid, amt, dt) in enumerate(raw_orders, 1)
    ]

    # 3. Insert into SQLite with strict schema, foreign keys, and batch transactions
    connection = sqlite3.connect(destination)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA journal_mode = MEMORY")
        connection.execute("PRAGMA cache_size = -64000")

        with connection:
            connection.executescript(
                "CREATE TABLE customers ("
                "customer_id INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "email TEXT"
                ");"
                "CREATE TABLE orders ("
                "order_id INTEGER PRIMARY KEY, "
                "customer_id INTEGER NOT NULL, "
                "amount REAL NOT NULL, "
                "order_date TEXT NOT NULL, "
                "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)"
                ");"
            )

            # Batch insert customers
            batch_size = 25000
            for i in range(0, len(customer_rows), batch_size):
                connection.executemany(
                    "INSERT INTO customers VALUES (?, ?, ?)",
                    customer_rows[i : i + batch_size],
                )

            # Batch insert orders
            for i in range(0, len(order_rows), batch_size):
                connection.executemany(
                    "INSERT INTO orders VALUES (?, ?, ?, ?)",
                    order_rows[i : i + batch_size],
                )

        # Integrity check on open read-write connection
        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key violations detected: {fk_errors}")

        # Compute summary metrics
        (actual_customers,) = connection.execute("SELECT COUNT(*) FROM customers").fetchone()
        (actual_orders, total_spending, min_amt, max_amt, avg_amt) = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0.0), COALESCE(MIN(amount), 0.0), "
            "COALESCE(MAX(amount), 0.0), COALESCE(AVG(amount), 0.0) FROM orders"
        ).fetchone()

        (inactive_count,) = connection.execute(
            "SELECT COUNT(*) FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id "
            "WHERE o.order_id IS NULL"
        ).fetchone()

    finally:
        connection.close()

    elapsed = perf_counter() - started
    file_size = destination.stat().st_size

    return GenerationSummary(
        db_path=destination,
        customers=actual_customers,
        orders=actual_orders,
        inactive_customers=inactive_count,
        active_customers=actual_customers - inactive_count,
        total_spending=round(total_spending, 2),
        min_order_amount=round(min_amt, 2),
        max_order_amount=round(max_amt, 2),
        mean_order_amount=round(avg_amt, 2),
        file_size_bytes=file_size,
        generation_time_s=round(elapsed, 3),
        synthetic_join_dates=synthetic_join_dates,
    )


def validate_large_database(
    db_path: str | Path,
    expected_customers: int,
    expected_orders: int,
    synthetic_join_dates: dict[int, date] | None = None,
) -> None:
    """Validate data integrity, schema equivalence, constraints, and temporal causality."""
    from src.db import connect_readonly

    conn = connect_readonly(db_path)
    try:
        # Schema checks
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}
        if tables != {"customers", "orders"}:
            raise AssertionError(f"Unexpected tables in database: {tables}")

        # Row counts
        (c_count,) = conn.execute("SELECT COUNT(*) FROM customers").fetchone()
        if c_count != expected_customers:
            raise AssertionError(f"Expected {expected_customers} customers, got {c_count}")

        (o_count,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        if o_count != expected_orders:
            raise AssertionError(f"Expected {expected_orders} orders, got {o_count}")

        # Foreign key integrity check via query (compatible with connect_readonly authorizer)
        (orphan_orders,) = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id NOT IN (SELECT customer_id FROM customers)"
        ).fetchone()
        if orphan_orders != 0:
            raise AssertionError(f"Found {orphan_orders} orphaned orders with invalid customer_id")

        # No NULLs in key fields
        (null_names,) = conn.execute("SELECT COUNT(*) FROM customers WHERE name IS NULL").fetchone()
        if null_names != 0:
            raise AssertionError(f"Found {null_names} customers with NULL names")

        (null_orders,) = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id IS NULL OR amount IS NULL OR order_date IS NULL"
        ).fetchone()
        if null_orders != 0:
            raise AssertionError(f"Found {null_orders} orders with NULL customer/amount/date")

        # Temporal causality: order_date >= synthetic_join_date
        if synthetic_join_dates and expected_orders > 0:
            for cid, o_date_str in conn.execute("SELECT customer_id, order_date FROM orders"):
                c_join = synthetic_join_dates[cid]
                o_date = date.fromisoformat(o_date_str)
                if o_date < c_join:
                    raise AssertionError(
                        f"Order date {o_date} precedes synthetic join date {c_join} for customer {cid}"
                    )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for seeding the large database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/large_analytics.db"),
        help="Destination database path (default: data/large_analytics.db)",
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=10000,
        help="Number of customers to generate (default: 10000)",
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=100000,
        help="Number of orders to generate (default: 100000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite destination database if it already exists",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed summary output",
    )
    args = parser.parse_args(argv)

    try:
        summary = seed_large_database(
            args.db,
            customers=args.customers,
            orders=args.orders,
            seed=args.seed,
            overwrite=args.overwrite,
        )
        validate_large_database(
            summary.db_path,
            args.customers,
            args.orders,
            summary.synthetic_join_dates,
        )
    except FileExistsError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Failed to generate large database: {err}", file=sys.stderr)
        return 2

    if not args.quiet:
        print("=" * 60)
        print("QueryMind Large Synthetic Database Generated Successfully")
        print("=" * 60)
        print(f"  Database path:       {summary.db_path}")
        print(f"  File size:           {summary.file_size_bytes / (1024 * 1024):.2f} MB ({summary.file_size_bytes:,} bytes)")
        print(f"  Generation time:     {summary.generation_time_s:.3f} s")
        print(f"  Customers:           {summary.customers:,}")
        print(f"  Active customers:    {summary.active_customers:,} ({summary.active_customers / summary.customers * 100:.1f}%)")
        print(f"  Inactive customers:  {summary.inactive_customers:,} ({summary.inactive_customers / summary.customers * 100:.1f}%)")
        print(f"  Orders:              {summary.orders:,}")
        if summary.orders > 0:
            print(f"  Total spending:      ${summary.total_spending:,.2f}")
            print(f"  Min order amount:    ${summary.min_order_amount:.2f}")
            print(f"  Max order amount:    ${summary.max_order_amount:,.2f}")
            print(f"  Mean order amount:   ${summary.mean_order_amount:.2f}")
        print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
