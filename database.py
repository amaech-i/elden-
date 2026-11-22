import os
import sqlite3

DATABASE = "elden.db"


def get_connection():
    if os.environ.get("DATABASE_URL"):
        from database_postgres import get_connection as postgres_connection
        return postgres_connection()

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables():
    if os.environ.get("DATABASE_URL"):
        from database_postgres import create_tables as verify_postgres_tables
        return verify_postgres_tables()

    connection = get_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                selling_price REAL NOT NULL,
                cost_price REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unit_cost REAL NOT NULL DEFAULT 0,
                business_id INTEGER REFERENCES businesses(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                total_amount REAL NOT NULL,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                line_total REAL NOT NULL,
                business_id INTEGER REFERENCES businesses(id),
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_name TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                reference TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                business_id INTEGER REFERENCES businesses(id),
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS business_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL UNIQUE
                    REFERENCES businesses(id),
                business_name TEXT NOT NULL DEFAULT 'My Business',
                phone TEXT,
                email TEXT,
                address TEXT,
                currency TEXT NOT NULL DEFAULT 'NGN',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)


        _create_phase10_tables(connection)
        connection.commit()

    finally:
        connection.close()


def _create_phase10_tables(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS subscription_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_code TEXT NOT NULL UNIQUE,
            plan_name TEXT NOT NULL,
            billing_cycle TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'NGN',
            duration_days INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL UNIQUE,
            plan_name TEXT NOT NULL DEFAULT 'free_trial',
            status TEXT NOT NULL DEFAULT 'trialing',
            trial_started_at TIMESTAMP NOT NULL,
            trial_ends_at TIMESTAMP NOT NULL,
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_id INTEGER,
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
        )
    """)


    connection.execute("""
        CREATE TABLE IF NOT EXISTS subscription_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'NGN',
            payment_reference TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            provider TEXT NOT NULL DEFAULT 'test',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP,
            FOREIGN KEY (business_id) REFERENCES businesses(id),
            FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
        )
    """)


if __name__ == "__main__":
    create_tables()
    print("Elden database tables are ready!")
