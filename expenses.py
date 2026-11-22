from database import get_connection


def add_expense(expense_name, amount, category, description="", business_id=None):
    expense_name = expense_name.strip()
    category = category.strip()
    description = description.strip()

    if not expense_name or not category:
        return False, "Expense name and category are required."

    if amount <= 0:
        return False, "Amount must be greater than zero."

    if business_id is None:
        return False, "Business account is required."

    connection = get_connection()

    try:
        connection.execute("""
            INSERT INTO expenses
            (expense_name, amount, category, description, business_id)
            VALUES (?, ?, ?, ?, ?)
        """, (expense_name, amount, category, description, business_id))

        connection.commit()
        return True, "Expense recorded successfully."

    finally:
        connection.close()


def get_all_expenses(business_id):
    connection = get_connection()

    try:
        return connection.execute("""
            SELECT * FROM expenses
            WHERE business_id = ?
            ORDER BY id DESC
        """, (business_id,)).fetchall()

    finally:
        connection.close()


def get_total_expenses(business_id):
    connection = get_connection()

    try:
        result = connection.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        return result["total"]

    finally:
        connection.close()


def get_expense_report(start_date, end_date, business_id):
    connection = get_connection()

    try:
        if hasattr(connection, "is_postgres"):
            date_condition = """
                created_at::date BETWEEN ?::date AND ?::date
            """
        else:
            date_condition = """
                DATE(created_at) BETWEEN DATE(?) AND DATE(?)
            """

        result = connection.execute(f"""
            SELECT
                COALESCE(SUM(amount), 0) AS total_expenses,
                COUNT(*) AS transactions
            FROM expenses
            WHERE {date_condition}
            AND business_id = ?
        """, (start_date, end_date, business_id)).fetchone()

        return dict(result)

    finally:
        connection.close()
