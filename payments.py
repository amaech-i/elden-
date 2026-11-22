from database import get_connection


def record_payment(invoice_id, amount, payment_method,
                   reference=None, business_id=None):

    if amount <= 0:
        return False, "Payment amount must be greater than zero."

    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        if hasattr(connection, "lock_row"):
            connection.execute("BEGIN")
            invoice = connection.lock_row("""
                SELECT total_amount
                FROM invoices
                WHERE id = ? AND business_id = ?
            """, (invoice_id, business_id)).fetchone()
        else:
            connection.execute("BEGIN IMMEDIATE")
            invoice = connection.execute("""
                SELECT total_amount
                FROM invoices
                WHERE id = ? AND business_id = ?
            """, (invoice_id, business_id)).fetchone()

        if invoice is None:
            connection.rollback()
            return False, "Invoice not found."

        total_paid = connection.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_paid
            FROM payments
            WHERE invoice_id = ? AND business_id = ?
        """, (invoice_id, business_id)).fetchone()["total_paid"]

        balance = invoice["total_amount"] - total_paid

        if amount > balance:
            connection.rollback()
            return False, "Payment exceeds the outstanding balance."

        connection.execute("""
            INSERT INTO payments (
                invoice_id, amount, payment_method,
                reference, business_id
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            invoice_id, amount, payment_method,
            reference, business_id
        ))

        new_total_paid = total_paid + amount

        if new_total_paid >= invoice["total_amount"]:
            status = "Paid"
        else:
            status = "Partially Paid"

        connection.execute("""
            UPDATE invoices
            SET payment_status = ?
            WHERE id = ? AND business_id = ?
        """, (status, invoice_id, business_id))

        connection.commit()
        return True, "Payment recorded successfully."

    except Exception as error:
        connection.rollback()
        return False, str(error)

    finally:
        connection.close()


def get_invoice_payments(invoice_id, business_id):
    connection = get_connection()

    try:
        return connection.execute("""
            SELECT *
            FROM payments
            WHERE invoice_id = ? AND business_id = ?
            ORDER BY id DESC
        """, (invoice_id, business_id)).fetchall()

    finally:
        connection.close()


def get_invoice_balance(invoice_id, business_id):
    connection = get_connection()

    try:
        invoice = connection.execute("""
            SELECT total_amount
            FROM invoices
            WHERE id = ? AND business_id = ?
        """, (invoice_id, business_id)).fetchone()

        if invoice is None:
            return None

        total_paid = connection.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_paid
            FROM payments
            WHERE invoice_id = ? AND business_id = ?
        """, (invoice_id, business_id)).fetchone()["total_paid"]

        return invoice["total_amount"] - total_paid

    finally:
        connection.close()
