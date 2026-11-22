import os
import psycopg
from psycopg.rows import dict_row


POSTGRES_DSN = os.environ.get(
    "DATABASE_URL",
    "host=127.0.0.1 port=5432 dbname=elden_test"
)


class DatabaseConnection:

    def __init__(self, connection):
        self.connection = connection
        self.is_postgres = True

    def execute(self, query, parameters=()):
        query = query.replace("?", "%s")
        query = query.replace("BEGIN IMMEDIATE", "BEGIN")
        return self.connection.execute(query, parameters)

    def lock_row(self, query, parameters=()):
        query = query.replace("?", "%s")
        query = query.rstrip().rstrip(";")
        return self.connection.execute(
            query + " FOR UPDATE",
            parameters
        )

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()
def get_connection():
    connection = psycopg.connect(
        POSTGRES_DSN,
        row_factory=dict_row
    )

    return DatabaseConnection(connection)


def create_tables():
    connection = get_connection()

    required_tables = [
        "businesses",
        "users",
        "products",
        "sales",
        "invoices",
        "invoice_items",
        "expenses",
        "customers",
        "payments",
        "business_settings",
        "subscription_plans",
        "subscriptions",
        "subscription_payments"
    ]

    try:
        result = connection.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)

        existing_tables = {
            row["table_name"] for row in result.fetchall()
        }

        missing_tables = [
            table for table in required_tables
            if table not in existing_tables
        ]

        if missing_tables:
            raise RuntimeError(
                f"Missing PostgreSQL tables: {missing_tables}"
            )

        print("PostgreSQL database tables verified.")

    finally:
        connection.close()
