
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql


BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = BASE_DIR / "elden.db"
POSTGRES_DSN = "host=127.0.0.1 port=5432 dbname=elden_test"

TABLES = [
    "businesses",
    "subscription_plans",
    "users",
    "products",
    "customers",
    "invoices",
    "expenses",
    "subscriptions",
    "business_settings",
    "invoice_items",
    "payments",
    "sales",
    "subscription_payments",
]


def migrate():
    if not SQLITE_PATH.exists():
        raise FileNotFoundError("Original SQLite database not found.")

    source = sqlite3.connect(SQLITE_PATH)
    target = psycopg.connect(POSTGRES_DSN)

    try:
        with target.transaction():

            # Make sure PostgreSQL is empty.
            for table in TABLES:
                count = target.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier(table)
                    )
                ).fetchone()[0]

                if count != 0:
                    raise RuntimeError(
                        f"{table} is not empty. Migration stopped."
                    )

            # Copy records in foreign-key dependency order.
            for table in TABLES:
                source_info = source.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()

                source_columns = [column[1] for column in source_info]

                target_columns = target.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table,)
                ).fetchall()

                target_column_names = [
                    column[0] for column in target_columns
                ]

                if source_columns != target_column_names:
                    raise RuntimeError(
                        f"Column mismatch in {table}. Migration stopped."
                    )

                rows = source.execute(
                    f'SELECT * FROM "{table}"'
                ).fetchall()

                if rows:
                    placeholders = sql.SQL(", ").join(
                        sql.Placeholder() for _ in source_columns
                    )

                    query = sql.SQL(
                        "INSERT INTO {} ({}) VALUES ({})"
                    ).format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(
                            sql.Identifier(column)
                            for column in source_columns
                        ),
                        placeholders
                    )

                    with target.cursor() as cursor:
                        cursor.executemany(query, rows)

                print(f"{table}: copied {len(rows)} records")

            # Reset identity sequences to the imported IDs.
            for table in TABLES:
                max_id = target.execute(
                    sql.SQL("SELECT MAX(id) FROM {}").format(
                        sql.Identifier(table)
                    )
                ).fetchone()[0]

                if max_id is not None:
                    sequence = target.execute(
                        "SELECT pg_get_serial_sequence(%s, 'id')",
                        (table,)
                    ).fetchone()[0]

                    target.execute(
                        "SELECT setval(%s, %s, true)",
                        (sequence, max_id)
                    )

        print("\nMigration completed successfully.")

    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    migrate()
