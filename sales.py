from database import get_connection


def is_postgres(connection):
    return hasattr(connection, "lock_row")

def record_sale(product_id, quantity, business_id):
    if quantity <= 0:
        return False, "Quantity must be greater than zero."

    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        connection.execute("BEGIN")

        if hasattr(connection, "lock_row"):
            product = connection.lock_row("""
                SELECT *
                FROM products
                WHERE id = ? AND business_id = ?
            """, (product_id, business_id)).fetchone()
        else:
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

        unit_price = product["selling_price"]
        total_amount = unit_price * quantity

        connection.execute("""
            INSERT INTO sales (
                product_id, product_name, quantity,
                unit_price, total_amount, unit_cost, business_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            product["name"],
            quantity,
            unit_price,
            total_amount,
            product["cost_price"],
            business_id
        ))

        connection.execute("""
            UPDATE products
            SET quantity = quantity - ?
            WHERE id = ? AND business_id = ?
        """, (quantity, product_id, business_id))

        connection.commit()
        return True, total_amount

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
def get_total_sales(business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT COALESCE(SUM(total_amount), 0) AS total
            FROM sales
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        return result["total"]

    finally:
        connection.close()

def get_total_cost_of_goods_sold(business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT COALESCE(SUM(quantity * unit_cost), 0) AS total
            FROM sales
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        return result["total"]

    finally:
        connection.close()

def get_profit_summary(business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(SUM(quantity * unit_cost), 0) AS cost
            FROM sales
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        expenses = connection.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        revenue = result["revenue"]
        cost = result["cost"]
        total_expenses = expenses["total"]

        gross_profit = revenue - cost
        net_profit = gross_profit - total_expenses

        return {
            "revenue": revenue,
            "cost_of_goods_sold": cost,
            "gross_profit": gross_profit,
            "expenses": total_expenses,
            "net_profit": net_profit
        }

    finally:
        connection.close()

def get_daily_sales_report(report_date, business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_sales,
                COUNT(*) AS transactions,
                COALESCE(SUM(quantity), 0) AS products_sold
            FROM sales
            WHERE DATE(created_at) = DATE(?)
              AND business_id = ?
        """, (report_date, business_id)).fetchone()

        return dict(result)

    finally:
        connection.close()

def get_weekly_sales_report(start_date, end_date, business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_sales,
                COUNT(*) AS transactions,
                COALESCE(SUM(quantity), 0) AS products_sold
            FROM sales
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
              AND business_id = ?
        """, (start_date, end_date, business_id)).fetchone()

        return dict(result)

    finally:
        connection.close()

def get_monthly_sales_report(year, month, business_id):
    connection = get_connection()

    try:
        if is_postgres(connection):
            date_condition = "EXTRACT(YEAR FROM created_at::timestamp) = ? AND EXTRACT(MONTH FROM created_at::timestamp) = ?"
        else:
            date_condition = "strftime('%Y', created_at) = ? AND strftime('%m', created_at) = ?"

        result = connection.execute(f"""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_sales,
                COUNT(*) AS transactions,
                COALESCE(SUM(quantity), 0) AS products_sold
            FROM sales
            WHERE {date_condition}
              AND business_id = ?
        """, (str(year), int(month) if is_postgres(connection) else str(month).zfill(2), business_id)).fetchone()

        return dict(result)

    finally:
        connection.close()

def get_profit_report(start_date, end_date, business_id):
    connection = get_connection()

    try:
        if is_postgres(connection):
            date_condition = 'created_at::date BETWEEN ?::date AND ?::date'
        else:
            date_condition = 'DATE(created_at) BETWEEN DATE(?) AND DATE(?)'

        sales = connection.execute(f"""
            SELECT
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(SUM(quantity * unit_cost), 0) AS cost
            FROM sales
            WHERE {date_condition}
              AND business_id = ?
        """, (start_date, end_date, business_id)).fetchone()

        expenses = connection.execute(f"""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE {date_condition}
              AND business_id = ?
        """, (start_date, end_date, business_id)).fetchone()

        revenue = sales['revenue']
        cost = sales['cost']
        total_expenses = expenses['total']
        gross_profit = revenue - cost

        return {
            'revenue': revenue,
            'cost_of_goods_sold': cost,
            'gross_profit': gross_profit,
            'expenses': total_expenses,
            'net_profit': gross_profit - total_expenses
        }

    finally:
        connection.close()

def get_best_selling_products(business_id, limit=10):
    connection = get_connection()

    try:
        results = connection.execute("""
            SELECT
                product_id,
                product_name,
                SUM(quantity) AS total_quantity_sold,
                SUM(total_amount) AS total_revenue
            FROM sales
            WHERE business_id = ?
            GROUP BY product_id, product_name
            ORDER BY total_quantity_sold DESC
            LIMIT ?
        """, (business_id, limit)).fetchall()

        return [dict(row) for row in results]

    finally:
        connection.close()
