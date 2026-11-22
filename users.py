from datetime import datetime, timedelta, timezone

from database import get_connection
from werkzeug.security import generate_password_hash, check_password_hash


def register_user(full_name, email, password):
    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name:
        return False, "Full name is required."

    if not email:
        return False, "Email is required."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    password_hash = generate_password_hash(password)
    connection = get_connection()

    try:
        connection.execute("BEGIN")

        cursor = connection.execute("""
            INSERT INTO businesses (business_name)
            VALUES (?)
            RETURNING id
        """, ("My Business",))

        business_id = cursor.fetchone()["id"]

        connection.execute("""
            INSERT INTO users (
                full_name,
                email,
                password_hash,
                business_id
            )
            VALUES (?, ?, ?, ?)
        """, (
            full_name,
            email,
            password_hash,
            business_id
        ))

        trial_started = datetime.now(timezone.utc)
        trial_ends = trial_started + timedelta(days=14)

        connection.execute("""
            INSERT INTO subscriptions (
                business_id,
                plan_name,
                status,
                trial_started_at,
                trial_ends_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            business_id,
            "free_trial",
            "trialing",
            trial_started.isoformat(),
            trial_ends.isoformat()
        ))

        connection.commit()
        return True, "Account created successfully."

    except Exception as error:
        connection.rollback()

        if (
            getattr(error, "sqlstate", None) == "23505"
            or "UNIQUE constraint failed" in str(error)
        ):
            return False, "Email is already registered."

        raise

    finally:
        connection.close()


def verify_login(email, password):
    connection = get_connection()

    try:
        user = connection.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email.strip().lower(),)).fetchone()

        if user is None:
            return None

        if check_password_hash(user["password_hash"], password):
            return dict(user)

        return None

    finally:
        connection.close()
