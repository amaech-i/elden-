import os
import re
import requests


PAYSTACK_BASE_URL = "https://api.paystack.co"


def initialize_transaction(email, amount_naira, reference, callback_url=None):
    secret_key = os.environ.get("PAYSTACK_SECRET_KEY", "")

    if not secret_key.startswith("sk_test_"):
        return False, "A Paystack test secret key is required."

    if not isinstance(amount_naira, int) or isinstance(amount_naira, bool):
        return False, "Amount must be a whole number."

    if amount_naira <= 0:
        return False, "Amount must be greater than zero."

    if not isinstance(email, str) or "@" not in email:
        return False, "A valid email address is required."

    if not isinstance(reference, str):
        return False, "Invalid payment reference."

    if not re.fullmatch(r"[A-Za-z0-9.=\\-]+", reference):
        return False, "Invalid payment reference."

    payload = {
        "email": email,
        "amount": amount_naira * 100,
        "currency": "NGN",
        "reference": reference
    }

    if callback_url:
        payload["callback_url"] = callback_url

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()
        result = response.json()

        if not result.get("status"):
            return False, "Paystack could not initialize the payment."

        data = result.get("data", {})

        if not data.get("authorization_url"):
            return False, "Paystack did not return a checkout URL."

        return True, data

    except requests.RequestException:
        return False, "Unable to connect to Paystack."

    except ValueError:
        return False, "Invalid response from Paystack."


def verify_transaction(reference):
    secret_key = os.environ.get("PAYSTACK_SECRET_KEY", "")

    if not secret_key.startswith("sk_test_"):
        return False, "A Paystack test secret key is required."

    if not isinstance(reference, str):
        return False, "Invalid payment reference."

    if not re.fullmatch(r"[A-Za-z0-9.=\\-]+", reference):
        return False, "Invalid payment reference."

    headers = {
        "Authorization": f"Bearer {secret_key}"
    }

    try:
        response = requests.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=15
        )

        response.raise_for_status()
        result = response.json()

        if not result.get("status"):
            return False, "Paystack could not verify this payment."

        return True, result.get("data", {})

    except requests.RequestException:
        return False, "Unable to connect to Paystack."

    except ValueError:
        return False, "Invalid response from Paystack."
