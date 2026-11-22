from database import get_connection


def add_product(name, selling_price, cost_price, quantity, business_id):
    connection = get_connection()

    connection.execute("""
        INSERT INTO products
        (name, selling_price, cost_price, quantity, business_id)
        VALUES (?, ?, ?, ?, ?)
    """, (name, selling_price, cost_price, quantity, business_id))

    connection.commit()
    connection.close()

    return "Product added successfully!"


def get_all_products(business_id):
    connection = get_connection()

    products = connection.execute("""
        SELECT * FROM products
        WHERE business_id = ?
        ORDER BY id DESC
    """, (business_id,)).fetchall()

    connection.close()
    return products


def get_inventory_stats(business_id):
    connection = get_connection()

    stats = connection.execute("""
        SELECT
            COUNT(*) AS total_products,
            COALESCE(SUM(quantity), 0) AS total_quantity,
            COALESCE(SUM(cost_price * quantity), 0) AS total_stock_value
        FROM products
        WHERE business_id = ?
    """, (business_id,)).fetchone()

    connection.close()
    return stats


def update_product(product_id, name, selling_price,
                   cost_price, quantity, business_id):
    connection = get_connection()

    cursor = connection.execute("""
        UPDATE products
        SET name = ?,
            selling_price = ?,
            cost_price = ?,
            quantity = ?
        WHERE id = ? AND business_id = ?
    """, (
        name, selling_price, cost_price,
        quantity, product_id, business_id
    ))

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    return updated > 0


def delete_product(product_id, business_id):
    connection = get_connection()

    cursor = connection.execute("""
        DELETE FROM products
        WHERE id = ? AND business_id = ?
    """, (product_id, business_id))

    connection.commit()
    deleted = cursor.rowcount
    connection.close()

    return deleted > 0


def update_stock(product_id, new_quantity, business_id):
    if new_quantity < 0:
        return False

    connection = get_connection()

    cursor = connection.execute("""
        UPDATE products
        SET quantity = ?
        WHERE id = ? AND business_id = ?
    """, (new_quantity, product_id, business_id))

    connection.commit()
    updated = cursor.rowcount
    connection.close()

    return updated > 0


def get_low_stock_products(business_id):
    connection = get_connection()

    products = connection.execute("""
        SELECT *
        FROM products
        WHERE quantity <= 5 AND business_id = ?
        ORDER BY quantity ASC
    """, (business_id,)).fetchall()

    connection.close()
    return products
