from database import get_connection


def create_plan(
    plan_code,
    plan_name,
    billing_cycle,
    price,
    duration_days,
    currency="NGN"
):
    plan_code = plan_code.strip().lower()
    plan_name = plan_name.strip()

    if not plan_code or not plan_name:
        return False, "Plan code and name are required."

    if billing_cycle not in ("monthly", "yearly"):
        return False, "Invalid billing cycle."

    if price < 0 or duration_days <= 0:
        return False, "Invalid price or duration."

    connection = get_connection()

    try:
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
        """, (
            plan_code,
            plan_name,
            billing_cycle,
            price,
            currency,
            duration_days,
            1
        ))

        connection.commit()
        return True, "Plan created successfully."

    except Exception as error:
        connection.rollback()

        if (
            getattr(error, "sqlstate", None) == "23505"
            or "UNIQUE constraint failed" in str(error)
        ):
            return False, "Plan code already exists."

        raise

    finally:
        connection.close()


def get_active_plans():
    connection = get_connection()

    try:
        plans = connection.execute("""
            SELECT *
            FROM subscription_plans
            WHERE is_active = 1
            ORDER BY price ASC
        """).fetchall()

        return [dict(plan) for plan in plans]

    finally:
        connection.close()


def get_plan_by_code(plan_code):
    connection = get_connection()

    try:
        plan = connection.execute("""
            SELECT *
            FROM subscription_plans
            WHERE plan_code = ?
            AND is_active = 1
        """, (plan_code,)).fetchone()

        return dict(plan) if plan else None

    finally:
        connection.close()


def update_plan_status(plan_code, is_active):
    connection = get_connection()

    try:
        cursor = connection.execute("""
            UPDATE subscription_plans
            SET is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE plan_code = ?
        """, (1 if is_active else 0, plan_code))

        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()
