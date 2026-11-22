import uuid
from database import get_connection


def create_invoice(customer_name, product_id, quantity, business_id):
    customer_name = customer_name.strip()

    if not customer_name:
        return False, "Customer name is required."

    if quantity <= 0:
        return False, "Quantity must be greater than zero."

    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        if hasattr(connection, "lock_row"):
            connection.execute("BEGIN")
            product = connection.lock_row("""
                SELECT *
                FROM products
                WHERE id = ? AND business_id = ?
            """, (product_id, business_id)).fetchone()
        else:
            connection.execute("BEGIN IMMEDIATE")
            product = connection.execute("""
                SELECT *
                FROM products
                WHERE id = ? AND business_id = ?
            """, (product_id, business_id)).fetchone()

        if product is None:
            connection.rollback()
            return False, "Product not found."

        if product["quantity"] < quantity:
            connection.rollback()
            return False, "Not enough stock available."

        total = product["selling_price"] * quantity
        invoice_number = "ELD-" + uuid.uuid4().hex[:10].upper()

        cursor = connection.execute("""
            INSERT INTO invoices
            (invoice_number, customer_name, total_amount, payment_status, business_id)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        """, (invoice_number, customer_name, total, 'Unpaid', business_id))

        invoice_id = cursor.fetchone()["id"]

        connection.execute("""
            INSERT INTO invoice_items
            (invoice_id, product_id, product_name,
             quantity, unit_price, line_total, business_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            product_id,
            product["name"],
            quantity,
            product["selling_price"],
            total,
            business_id
        ))

        connection.execute("""
            INSERT INTO sales
            (product_id, product_name, quantity,
             unit_price, total_amount, unit_cost, business_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            product["name"],
            quantity,
            product["selling_price"],
            total,
            product["cost_price"],
            business_id
        ))

        connection.execute("""
            UPDATE products
            SET quantity = quantity - ?
            WHERE id = ? AND business_id = ?
        """, (quantity, product_id, business_id))

        connection.commit()
        return True, invoice_number

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def update_invoice_status(invoice_id, status):
    return False, "Invoice status is updated automatically through recorded payments."


def get_customer_debts(business_id):
    connection = get_connection()

    try:
        debts = connection.execute("""
            SELECT
                invoices.customer_name,
                SUM(
                    invoices.total_amount -
                    COALESCE(payment_totals.total_paid, 0)
                ) AS total_owed,
                COUNT(*) AS unpaid_invoices
            FROM invoices
            LEFT JOIN (
                SELECT
                    invoice_id,
                    SUM(amount) AS total_paid
                FROM payments
                WHERE business_id = ?
                GROUP BY invoice_id
            ) AS payment_totals
            ON invoices.id = payment_totals.invoice_id
            WHERE invoices.business_id = ?
            AND invoices.total_amount >
                COALESCE(payment_totals.total_paid, 0)
            GROUP BY invoices.customer_name
            ORDER BY total_owed DESC
        """, (business_id, business_id)).fetchall()

        return debts

    finally:
        connection.close()


def get_customer_invoices(customer_name, business_id):
    connection = get_connection()

    try:
        return connection.execute("""
            SELECT *
            FROM invoices
            WHERE customer_name = ?
            AND business_id = ?
            ORDER BY id DESC
        """, (customer_name, business_id)).fetchall()

    finally:
        connection.close()
