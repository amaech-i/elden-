from database import get_connection


def add_customer(name, phone="", email="", address="", business_id=None):
    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        connection.execute("""
            INSERT INTO customers
            (name, phone, email, address, business_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, phone, email, address, business_id))

        connection.commit()
        return True, "Customer added successfully!"

    finally:
        connection.close()


def get_all_customers(business_id):
    connection = get_connection()

    try:
        return connection.execute("""
            SELECT * FROM customers
            WHERE business_id = ?
            ORDER BY id DESC
        """, (business_id,)).fetchall()

    finally:
        connection.close()


def update_customer(customer_id, name, phone="", email="",
                    address="", business_id=None):
    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        result = connection.execute("""
            UPDATE customers
            SET name = ?, phone = ?, email = ?, address = ?
            WHERE id = ? AND business_id = ?
        """, (name, phone, email, address, customer_id, business_id))

        connection.commit()

        if result.rowcount == 0:
            return False, "Customer not found"

        return True, "Customer updated successfully!"

    finally:
        connection.close()


def delete_customer(customer_id, business_id):
    connection = get_connection()

    try:
        customer = connection.execute("""
            SELECT name FROM customers
            WHERE id = ? AND business_id = ?
        """, (customer_id, business_id)).fetchone()

        if customer is None:
            return False, "Customer not found"

        invoice = connection.execute("""
            SELECT id FROM invoices
            WHERE customer_name = ? AND business_id = ?
            LIMIT 1
        """, (customer["name"], business_id)).fetchone()

        if invoice:
            return False, "Cannot delete customer with existing invoices"

        connection.execute("""
            DELETE FROM customers
            WHERE id = ? AND business_id = ?
        """, (customer_id, business_id))

        connection.commit()
        return True, "Customer deleted successfully!"

    finally:
        connection.close()
