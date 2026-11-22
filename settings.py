from database import get_connection


def get_business_settings(business_id):
    connection = get_connection()

    try:
        connection.execute("""
            INSERT INTO business_settings (business_id, business_name, currency)
            SELECT id, business_name, 'NGN'
            FROM businesses
            WHERE id = ?
            ON CONFLICT (business_id) DO NOTHING
        """, (business_id,))

        connection.commit()

        settings = connection.execute("""
            SELECT *
            FROM business_settings
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        return dict(settings) if settings else None

    finally:
        connection.close()


def update_business_settings(
    business_name,
    phone,
    email,
    address,
    currency,
    business_id
):
    if not business_name.strip():
        return False, "Business name is required."

    if currency not in ("NGN", "USD", "GBP", "EUR"):
        return False, "Invalid currency."

    connection = get_connection()

    try:
        cursor = connection.execute("""
            UPDATE business_settings
            SET
                business_name = ?,
                phone = ?,
                email = ?,
                address = ?,
                currency = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE business_id = ?
        """, (
            business_name.strip(),
            phone.strip(),
            email.strip(),
            address.strip(),
            currency,
            business_id
        ))

        connection.commit()

        if cursor.rowcount == 0:
            return False, "Business settings not found."

        return True, "Business settings updated successfully."

    finally:
        connection.close()
