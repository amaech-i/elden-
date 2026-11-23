import os
from database import get_connection

if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("PostgreSQL DATABASE_URL is required.")

PLANS = [
    ("starter", "Starter", "monthly", 5000, "NGN", 30, 1),
    ("business", "Business", "monthly", 10000, "NGN", 30, 1),
    ("professional", "Professional", "monthly", 20000, "NGN", 30, 1),
]

connection = get_connection()

try:
    for plan in PLANS:
        connection.execute("""
            INSERT INTO subscription_plans (
                plan_code,
                plan_name,
                billing_cycle,
                price,
                currency,
                duration_days,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (plan_code) DO NOTHING
        """, plan)

    connection.commit()
    print("Production subscription plans verified.")

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()
