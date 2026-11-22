from datetime import datetime, timezone
from database import get_connection


def subscription_allows_access(business_id):
    connection = get_connection()

    try:
        subscription = connection.execute("""
            SELECT status, trial_ends_at, current_period_end
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return False, "No subscription found."

        now = datetime.now(timezone.utc)
        status = subscription["status"]

        if status == "trialing":
            end_date = subscription["trial_ends_at"]

        elif status == "active":
            end_date = subscription["current_period_end"]

        else:
            return False, "Subscription is not active."

        if not end_date:
            return False, "Subscription end date is missing."

        end_date = datetime.fromisoformat(end_date)

        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        if end_date > now:
            return True, "Subscription access allowed."

        return False, "Subscription has expired."

    finally:
        connection.close()


def get_subscription(business_id):
    connection = get_connection()

    try:
        subscription = connection.execute("""
            SELECT *
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return None

        return dict(subscription)

    finally:
        connection.close()


def get_subscription_details(business_id):
    connection = get_connection()

    try:
        subscription = connection.execute("""
            SELECT
                subscriptions.*,
                subscription_plans.plan_code,
                subscription_plans.billing_cycle,
                subscription_plans.price,
                subscription_plans.currency,
                subscription_plans.duration_days
            FROM subscriptions
            LEFT JOIN subscription_plans
                ON subscriptions.plan_id = subscription_plans.id
            WHERE subscriptions.business_id = ?
        """, (business_id,)).fetchone()

        return dict(subscription) if subscription else None

    finally:
        connection.close()


def select_subscription_plan(business_id, plan_code):
    connection = get_connection()

    try:
        plan = connection.execute("""
            SELECT id, plan_name
            FROM subscription_plans
            WHERE plan_code = ? AND is_active = 1
        """, (plan_code,)).fetchone()

        if plan is None:
            return False, "Selected plan is unavailable."

        subscription = connection.execute("""
            SELECT id, status
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return False, "No subscription found."

        if subscription["status"] == "active":
            return False, "Your paid subscription is already active."

        connection.execute("""
            UPDATE subscriptions
            SET plan_id = ?,
                plan_name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE business_id = ?
        """, (plan["id"], plan["plan_name"], business_id))

        connection.commit()

        return True, "Plan selected successfully. Payment is still required."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
