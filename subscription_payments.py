import uuid

from database import get_connection
from plans import get_plan_by_code


def select_for_update(connection, query, parameters=()):
    if hasattr(connection, "lock_row"):
        return connection.lock_row(query, parameters)

    return connection.execute(query, parameters)


def create_test_payment(business_id, plan_code):
    plan = get_plan_by_code(plan_code)

    if plan is None:
        return False, "Selected plan is unavailable."

    payment_reference = "ELDEN-TEST-" + uuid.uuid4().hex[:16].upper()

    connection = get_connection()

    try:
        subscription = connection.execute("""
            SELECT id
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return False, "No subscription found."

        connection.execute("""
            INSERT INTO subscription_payments (
                business_id,
                plan_id,
                amount,
                currency,
                payment_reference,
                status,
                provider
            )
            VALUES (?, ?, ?, ?, ?, 'pending', 'test')
        """, (
            business_id,
            plan["id"],
            plan["price"],
            plan["currency"],
            payment_reference
        ))

        connection.commit()
        return True, payment_reference

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def verify_test_payment(business_id, payment_reference):
    from datetime import datetime, timedelta, timezone

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        payment = select_for_update(connection, """
            SELECT
                spay.*,
                plans.plan_name,
                plans.price AS plan_price,
                plans.currency AS plan_currency,
                plans.duration_days,
                plans.is_active
            FROM subscription_payments AS spay
            JOIN subscription_plans AS plans
                ON plans.id = spay.plan_id
            WHERE spay.business_id = ?
              AND spay.payment_reference = ?
              AND spay.provider = 'test'
              AND spay.status = 'pending'
        """, (business_id, payment_reference)).fetchone()

        if payment is None:
            return False, "Pending test payment not found."

        if not payment["is_active"]:
            return False, "Selected plan is no longer available."

        if (
            payment["amount"] != payment["plan_price"]
            or payment["currency"] != payment["plan_currency"]
        ):
            return False, "Payment amount or currency mismatch."

        subscription = select_for_update(connection, """
            SELECT id, status, current_period_end
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return False, "Subscription not found."

        now = datetime.now(timezone.utc)
        period_start = now
        existing_end = subscription["current_period_end"]

        if subscription["status"] == "active" and existing_end:
            existing_end = datetime.fromisoformat(existing_end)

            if existing_end.tzinfo is None:
                existing_end = existing_end.replace(
                    tzinfo=timezone.utc
                )

            if existing_end > now:
                period_start = existing_end

        period_end = period_start + timedelta(
            days=payment["duration_days"]
        )

        cursor = connection.execute("""
            UPDATE subscription_payments
            SET status = 'successful',
                verified_at = ?
            WHERE id = ?
              AND status = 'pending'
        """, (now.isoformat(), payment["id"]))

        if cursor.rowcount != 1:
            connection.rollback()
            return False, "Payment has already been processed."

        connection.execute("""
            UPDATE subscriptions
            SET plan_id = ?,
                plan_name = ?,
                status = 'active',
                current_period_start = ?,
                current_period_end = ?
            WHERE business_id = ?
        """, (
            payment["plan_id"],
            payment["plan_name"],
            period_start.isoformat(),
            period_end.isoformat(),
            business_id
        ))

        connection.commit()

        return True, "Test payment verified and subscription activated."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_test_payment(business_id, payment_reference):
    connection = get_connection()

    try:
        payment = connection.execute("""
            SELECT
                payments.payment_reference,
                payments.amount,
                payments.currency,
                payments.status,
                plans.plan_name,
                plans.billing_cycle
            FROM subscription_payments AS payments
            JOIN subscription_plans AS plans
                ON plans.id = payments.plan_id
            WHERE payments.business_id = ?
              AND payments.payment_reference = ?
              AND payments.provider = 'test'
        """, (business_id, payment_reference)).fetchone()

        return dict(payment) if payment else None

    finally:
        connection.close()


def get_payment_history(business_id):
    connection = get_connection()

    try:
        payments = connection.execute("""
            SELECT
                subscription_payments.payment_reference,
                subscription_payments.amount,
                subscription_payments.currency,
                subscription_payments.status,
                subscription_payments.provider,
                subscription_payments.created_at,
                subscription_payments.verified_at,
                subscription_plans.plan_name,
                subscription_plans.billing_cycle
            FROM subscription_payments
            JOIN subscription_plans
                ON subscription_payments.plan_id = subscription_plans.id
            WHERE subscription_payments.business_id = ?
            ORDER BY
                subscription_payments.created_at DESC,
                subscription_payments.id DESC
        """, (business_id,)).fetchall()

        return [dict(payment) for payment in payments]

    finally:
        connection.close()


def create_paystack_payment(business_id, plan_code):
    plan = get_plan_by_code(plan_code)

    if plan is None:
        return False, "Selected plan is unavailable."

    payment_reference = (
        "ELDEN-PAYSTACK-" + uuid.uuid4().hex[:16].upper()
    )

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        subscription = connection.execute("""
            SELECT id
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            return False, "No subscription found."

        connection.execute("""
            INSERT INTO subscription_payments (
                business_id,
                plan_id,
                amount,
                currency,
                payment_reference,
                status,
                provider
            )
            VALUES (?, ?, ?, ?, ?, 'pending', 'paystack')
        """, (
            business_id,
            plan["id"],
            plan["price"],
            plan["currency"],
            payment_reference
        ))

        connection.commit()
        return True, payment_reference

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def verify_paystack_payment(business_id, payment_reference):
    from datetime import datetime, timedelta, timezone
    from paystack import verify_transaction

    connection = get_connection()

    try:
        payment = connection.execute("""
            SELECT
                sp.id,
                sp.plan_id,
                sp.amount,
                sp.currency,
                plans.plan_name,
                plans.price AS plan_price,
                plans.currency AS plan_currency,
                plans.duration_days,
                plans.is_active
            FROM subscription_payments AS sp
            JOIN subscription_plans AS plans
                ON plans.id = sp.plan_id
            WHERE sp.business_id = ?
              AND sp.payment_reference = ?
              AND sp.provider = 'paystack'
              AND sp.status = 'pending'
        """, (business_id, payment_reference)).fetchone()

    finally:
        connection.close()

    if payment is None:
        return False, "Pending Paystack payment not found."

    if not payment["is_active"]:
        return False, "Selected plan is no longer available."

    if (
        payment["amount"] != payment["plan_price"]
        or payment["currency"] != payment["plan_currency"]
        or payment["currency"] != "NGN"
    ):
        return False, "Payment amount or currency mismatch."

    verified, data = verify_transaction(payment_reference)

    if not verified:
        return False, data

    if data.get("status") != "success":
        return False, "Paystack payment is not successful."

    if data.get("reference") != payment_reference:
        return False, "Payment reference mismatch."

    if data.get("amount") != payment["amount"] * 100:
        return False, "Payment amount mismatch."

    if data.get("currency") != payment["currency"]:
        return False, "Payment currency mismatch."

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        current_payment = select_for_update(connection, """
            SELECT
                sp.id,
                sp.plan_id,
                sp.amount,
                sp.currency,
                plans.plan_name,
                plans.price AS plan_price,
                plans.currency AS plan_currency,
                plans.duration_days,
                plans.is_active
            FROM subscription_payments AS sp
            JOIN subscription_plans AS plans
                ON plans.id = sp.plan_id
            WHERE sp.business_id = ?
              AND sp.payment_reference = ?
              AND sp.provider = 'paystack'
              AND sp.status = 'pending'
        """, (business_id, payment_reference)).fetchone()

        if current_payment is None:
            connection.rollback()
            return False, "Payment has already been processed."

        if (
            not current_payment["is_active"]
            or current_payment["amount"] != current_payment["plan_price"]
            or current_payment["currency"] != current_payment["plan_currency"]
            or current_payment["currency"] != "NGN"
        ):
            connection.rollback()
            return False, "Payment details are no longer valid."

        subscription = select_for_update(connection, """
            SELECT id, status, current_period_end
            FROM subscriptions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if subscription is None:
            connection.rollback()
            return False, "Subscription not found."

        now = datetime.now(timezone.utc)
        period_start = now
        existing_end = subscription["current_period_end"]

        if subscription["status"] == "active" and existing_end:
            existing_end = datetime.fromisoformat(existing_end)

            if existing_end.tzinfo is None:
                existing_end = existing_end.replace(
                    tzinfo=timezone.utc
                )

            if existing_end > now:
                period_start = existing_end

        period_end = period_start + timedelta(
            days=current_payment["duration_days"]
        )

        cursor = connection.execute("""
            UPDATE subscription_payments
            SET status = 'successful',
                verified_at = ?
            WHERE id = ?
              AND status = 'pending'
              AND provider = 'paystack'
        """, (now.isoformat(), current_payment["id"]))

        if cursor.rowcount != 1:
            connection.rollback()
            return False, "Payment has already been processed."

        connection.execute("""
            UPDATE subscriptions
            SET plan_id = ?,
                plan_name = ?,
                status = 'active',
                current_period_start = ?,
                current_period_end = ?
            WHERE business_id = ?
        """, (
            current_payment["plan_id"],
            current_payment["plan_name"],
            period_start.isoformat(),
            period_end.isoformat(),
            business_id
        ))

        connection.commit()

        return True, "Paystack payment verified and subscription activated."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_paystack_payment(business_id, payment_reference):
    connection = get_connection()

    try:
        payment = connection.execute("""
            SELECT
                sp.payment_reference,
                sp.amount,
                sp.currency,
                sp.status,
                sp.provider,
                plans.plan_name,
                plans.billing_cycle
            FROM subscription_payments AS sp
            JOIN subscription_plans AS plans
                ON plans.id = sp.plan_id
            WHERE sp.business_id = ?
              AND sp.payment_reference = ?
              AND sp.provider = 'paystack'
            LIMIT 1
        """, (business_id, payment_reference)).fetchone()

        return dict(payment) if payment else None

    finally:
        connection.close()


def mark_paystack_payment_failed(business_id, payment_reference):
    connection = get_connection()

    try:
        cursor = connection.execute("""
            UPDATE subscription_payments
            SET status = 'failed'
            WHERE business_id = ?
              AND payment_reference = ?
              AND provider = 'paystack'
              AND status = 'pending'
        """, (business_id, payment_reference))

        connection.commit()
        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
