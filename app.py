from datetime import timedelta
from flask_wtf.csrf import CSRFProtect
import os
import hashlib
import hmac
from urllib.parse import urlparse
from functools import wraps
from expenses import add_expense, get_all_expenses
from flask import Flask, render_template, request, redirect, url_for, session
from payments import get_invoice_payments, get_invoice_balance
from database import create_tables, get_connection
from settings import get_business_settings, update_business_settings
from products import (
    add_product,
    get_all_products,
    update_product,
    delete_product,
    get_low_stock_products
)

from sales import (
    record_sale,
    get_profit_summary,
    get_daily_sales_report,
    get_weekly_sales_report,
    get_monthly_sales_report,
    get_profit_report,
    get_best_selling_products
)
from expenses import get_expense_report
from invoices import create_invoice, update_invoice_status, get_customer_debts, get_customer_invoices
from customers import add_customer, get_all_customers, update_customer, delete_customer
from users import register_user, verify_login
from subscriptions import (
    subscription_allows_access,
    get_subscription_details,
    select_subscription_plan
)
from plans import get_active_plans
from subscription_payments import (
    create_test_payment,
    get_test_payment,
    verify_test_payment,
    create_paystack_payment,
    verify_paystack_payment,
    get_payment_history,
    get_paystack_payment,
    mark_paystack_payment_failed
)
from paystack import initialize_transaction

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session or "business_id" not in session:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def subscription_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        allowed, message = subscription_allows_access(
            session["business_id"]
        )

        if not allowed:
            business_id = session["business_id"]
            subscription = get_subscription_details(business_id)
            payments = get_payment_history(business_id)

            return render_template(
                "subscription.html",
                subscription=subscription,
                payments=payments
            ), 403

        return view(*args, **kwargs)

    return wrapped_view

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("ELDEN_SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("ELDEN_SECRET_KEY is not configured.")


csrf = CSRFProtect(app)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("ELDEN_ENV") == "production"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

create_tables()



@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user = verify_login(email, password)

        if user:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["business_id"] = user["business_id"]

            return redirect(url_for("home"))

        error = "Invalid email or password."

    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        success, message = register_user(
            full_name,
            email,
            password
        )

        if success:
            return redirect(url_for("login"))

        error = message

    return render_template("register.html", error=error)

@app.route("/plans")
@login_required
def plans_page():
    plans = get_active_plans()

    return render_template(
        "plans.html",
        plans=plans
    )


@app.route("/paystack-checkout", methods=["POST"])
@login_required
def paystack_checkout():
    if os.environ.get("ELDEN_ENV") == "production":
        return "Paystack test checkout is disabled in production.", 403

    if not os.environ.get("PAYSTACK_SECRET_KEY", "").startswith("sk_test_"):
        return "Paystack test secret key is not configured.", 503

    plan_code = request.form.get("plan_code", "").strip()

    if not plan_code:
        return redirect(url_for("plans_page"))

    success, payment_reference = create_paystack_payment(
        session["business_id"],
        plan_code
    )

    if not success:
        return payment_reference, 400

    payment = get_paystack_payment(
        session["business_id"],
        payment_reference
    )

    connection = get_connection()

    try:
        user = connection.execute("""
            SELECT email
            FROM users
            WHERE id = ?
              AND business_id = ?
        """, (
            session["user_id"],
            session["business_id"]
        )).fetchone()
    finally:
        connection.close()

    if payment is None or user is None:
        mark_paystack_payment_failed(
            session["business_id"],
            payment_reference
        )
        return "Unable to retrieve payment details.", 400

    success, result = initialize_transaction(
        user["email"],
        payment["amount"],
        payment_reference,
        callback_url=url_for(
            "paystack_callback",
            _external=True
        )
    )

    if not success:
        mark_paystack_payment_failed(
            session["business_id"],
            payment_reference
        )
        return result, 400

    checkout_url = result.get("authorization_url", "")
    parsed_url = urlparse(checkout_url)

    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "checkout.paystack.com"
    ):
        mark_paystack_payment_failed(
            session["business_id"],
            payment_reference
        )
        return "Invalid Paystack checkout URL.", 400

    return redirect(checkout_url)


@app.route("/select-plan", methods=["POST"])
@login_required
def select_plan():
    if os.environ.get("ELDEN_ENV") == "production":
        return "Test payments are disabled.", 403

    plan_code = request.form.get("plan_code", "").strip()

    if not plan_code:
        return redirect(url_for("plans_page"))

    success, message = select_subscription_plan(
        session["business_id"],
        plan_code
    )

    if not success:
        return render_template(
            "plans.html",
            plans=get_active_plans(),
            error=message
        ), 400

    success, payment_reference = create_test_payment(
        session["business_id"],
        plan_code
    )

    if not success:
        return payment_reference, 400

    return redirect(url_for(
        "checkout_page",
        payment_reference=payment_reference
    ))


@app.route("/checkout/<payment_reference>")
@login_required
def checkout_page(payment_reference):
    if os.environ.get("ELDEN_ENV") == "production":
        return "Test payments are disabled.", 403

    payment = get_test_payment(
        session["business_id"],
        payment_reference
    )

    if payment is None:
        return "Payment not found.", 404

    return render_template(
        "checkout.html",
        payment=payment
    )


@app.route("/complete-test-payment/<payment_reference>", methods=["POST"])
@login_required
def complete_test_payment(payment_reference):
    if os.environ.get("ELDEN_ENV") == "production":
        return "Test payments are disabled.", 403

    success, message = verify_test_payment(
        session["business_id"],
        payment_reference
    )

    if not success:
        return message, 400

    return redirect(url_for(
        "checkout_page",
        payment_reference=payment_reference
    ))

@app.route("/subscription")
@login_required
def subscription_page():
    business_id = session["business_id"]
    subscription = get_subscription_details(business_id)
    payments = get_payment_history(business_id)
    access_allowed, access_message = subscription_allows_access(business_id)

    return render_template(
        "subscription.html",
        subscription=subscription,
        payments=payments,
        access_allowed=access_allowed
    )

@app.route("/paystack/webhook", methods=["POST"])
@csrf.exempt
def paystack_webhook():
    if os.environ.get("ELDEN_ENV") == "production":
        return "Test webhook disabled in production.", 403

    secret_key = os.environ.get("PAYSTACK_SECRET_KEY", "")

    if not secret_key.startswith("sk_test_"):
        return "Paystack test key is not configured.", 503

    signature = request.headers.get("x-paystack-signature", "")
    payload = request.get_data()

    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()

    if not signature or not hmac.compare_digest(
        signature,
        expected_signature
    ):
        return "Invalid webhook signature.", 401

    event_data = request.get_json(silent=True)

    if not isinstance(event_data, dict):
        return "Invalid webhook payload.", 400

    if event_data.get("event") != "charge.success":
        return "Event ignored.", 200

    data = event_data.get("data")

    if not isinstance(data, dict):
        return "Invalid event data.", 400

    payment_reference = data.get("reference")

    if not isinstance(payment_reference, str) or not payment_reference:
        return "Payment reference missing.", 400

    connection = get_connection()

    try:
        payment = connection.execute("""
            SELECT business_id, status
            FROM subscription_payments
            WHERE payment_reference = ?
              AND provider = 'paystack'
            LIMIT 1
        """, (payment_reference,)).fetchone()
    finally:
        connection.close()

    if payment is None:
        return "Payment not found.", 404

    if payment["status"] == "successful":
        return "Payment already processed.", 200

    if payment["status"] != "pending":
        return "Payment is not pending.", 200

    success, message = verify_paystack_payment(
        payment["business_id"],
        payment_reference
    )

    if not success:
        return "Payment verification failed.", 400

    return "Webhook payment verified.", 200


@app.route("/paystack/callback")
@login_required
def paystack_callback():
    payment_reference = request.args.get("reference", "").strip()

    if not payment_reference:
        return render_template(
            "payment_result.html",
            success=False,
            message="Payment reference is missing.",
            payment_reference=None
        ), 400

    success, message = verify_paystack_payment(
        session["business_id"],
        payment_reference
    )

    return render_template(
        "payment_result.html",
        success=success,
        message=message,
        payment_reference=payment_reference
    ), 200 if success else 400


@app.route("/")
@login_required
@subscription_required
def home():
    summary = get_profit_summary(session["business_id"])
    products = get_all_products(session["business_id"])

    return render_template(
        "index.html",
        summary=summary,
        total_products=len(products)
    )

@app.route("/inventory")
@login_required
@subscription_required
def inventory():
    products = get_all_products(session["business_id"])
    low_stock_products = get_low_stock_products(session["business_id"])

    return render_template(
        "inventory.html",
        products=products,
        low_stock_products=low_stock_products
    )

@app.route("/inventory/add", methods=["POST"])
@login_required
@subscription_required
def add_inventory_product():
    name = request.form.get("name", "").strip()

    try:
        selling_price = float(request.form["selling_price"])
        cost_price = float(request.form["cost_price"])
        quantity = int(request.form["quantity"])

        if not name or selling_price < 0 or cost_price < 0 or quantity < 0:
            return "Invalid product details", 400

    except (ValueError, KeyError):
        return "Please enter valid product details", 400

    add_product(name, selling_price, cost_price, quantity, session["business_id"])
    return redirect(url_for("inventory"))

@app.route("/inventory/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
@subscription_required
def edit_inventory_product(product_id):
    products = get_all_products(session["business_id"])
    product = next((p for p in products if p["id"] == product_id), None)

    if product is None:
        return "Product not found", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        try:
            selling_price = float(request.form["selling_price"])
            cost_price = float(request.form["cost_price"])
            quantity = int(request.form["quantity"])

            if not name or selling_price < 0 or cost_price < 0 or quantity < 0:
                return "Invalid product details", 400

        except (ValueError, KeyError):
            return "Please enter valid product details", 400

        update_product(product_id, name, selling_price, cost_price, quantity, session["business_id"])
        return redirect(url_for("inventory"))

    return render_template("edit_product.html", product=product)

@app.route("/inventory/delete/<int:product_id>", methods=["POST"])
@login_required
@subscription_required
def delete_inventory_product(product_id):
    delete_product(product_id, session["business_id"])
    return redirect(url_for("inventory"))



@app.route("/sales", methods=["GET", "POST"])
@login_required
@subscription_required
def sales_page():
    from database import get_connection

    if request.method == "POST":
        try:
            product_id = int(request.form["product_id"])
            quantity = int(request.form["quantity"])
        except (ValueError, KeyError):
            return "Please enter valid sale details", 400

        success, result = record_sale(product_id, quantity, session["business_id"])

        if not success:
            return result, 400

        return redirect(url_for("sales_page"))

    products = get_all_products(session["business_id"])

    connection = get_connection()
    sales = connection.execute(
        "SELECT * FROM sales WHERE business_id = ? ORDER BY id DESC",
        (session["business_id"],)
    ).fetchall()
    connection.close()

    return render_template(
        "sales.html",
        products=products,
        sales=sales
    )



@app.route("/invoices", methods=["GET", "POST"])
@login_required
@subscription_required
def invoices_page():
    from database import get_connection

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "")

        try:
            product_id = int(request.form["product_id"])
            quantity = int(request.form["quantity"])
        except (ValueError, KeyError):
            return "Please enter valid invoice details", 400

        success, result = create_invoice(
            customer_name, product_id, quantity, session["business_id"]
        )

        if not success:
            return result, 400

        return redirect(url_for("invoices_page"))

    products = get_all_products(session["business_id"])

    connection = get_connection()
    invoices = connection.execute(
        "SELECT * FROM invoices WHERE business_id = ? ORDER BY id DESC",
        (session["business_id"],)
    ).fetchall()
    connection.close()

    return render_template(
        "invoices.html",
        products=products,
        invoices=invoices
    )



@app.route("/invoices/<int:invoice_id>")
@login_required
@subscription_required
def invoice_details(invoice_id):
    from database import get_connection

    connection = get_connection()

    invoice = connection.execute(
        "SELECT * FROM invoices WHERE id = ? AND business_id = ?",
        (invoice_id, session["business_id"])
    ).fetchone()

    if invoice is None:
        connection.close()
        return "Invoice not found", 404

    items = connection.execute(
        "SELECT * FROM invoice_items WHERE invoice_id = ? AND business_id = ?",
        (invoice_id, session["business_id"])
    ).fetchall()

    connection.close()

    return render_template(
        "invoice_details.html",
        invoice=invoice,
        items=items,
        settings=get_business_settings(session["business_id"]),
        payments=get_invoice_payments(invoice_id, session["business_id"]),
        balance=get_invoice_balance(invoice_id, session["business_id"])
    )



@app.route("/invoices/<int:invoice_id>/payment", methods=["POST"])
@login_required
@subscription_required
def record_invoice_payment(invoice_id):
    from payments import record_payment

    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        return "Invalid payment amount", 400

    payment_method = request.form.get("payment_method", "").strip()
    reference = request.form.get("reference", "").strip() or None

    if not payment_method:
        return "Payment method is required", 400

    success, message = record_payment(
        invoice_id,
        amount,
        payment_method,
        reference,
        session["business_id"]
    )

    if not success:
        return message, 400

    return redirect(url_for("invoice_details", invoice_id=invoice_id))



@app.route("/invoices/<int:invoice_id>/status", methods=["POST"])
@login_required
@subscription_required
def change_invoice_status(invoice_id):
    status = request.form.get("status", "")

    success, message = update_invoice_status(invoice_id, status)

    if not success:
        return message, 400

    return redirect(url_for("invoices_page"))



@app.route("/debts")
@login_required
@subscription_required
def customer_debts_page():
    debts = get_customer_debts(session["business_id"])

    return render_template(
        "debts.html",
        debts=debts
    )



@app.route("/expenses", methods=["GET", "POST"])
@login_required
@subscription_required
def expenses_page():
    if request.method == "POST":
        expense_name = request.form.get("expense_name", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "")

        try:
            amount = float(request.form["amount"])
            if amount <= 0:
                return "Amount must be greater than zero", 400
        except (ValueError, KeyError):
            return "Please enter a valid amount", 400

        success, message = add_expense(
            expense_name, amount, category, description, session["business_id"]
        )

        if not success:
            return message, 400

        return redirect(url_for("expenses_page"))

    expenses = get_all_expenses(session["business_id"])
    return render_template("expenses.html", expenses=expenses)



@app.route("/customers", methods=["GET", "POST"])
@login_required
@subscription_required
def customers_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            return "Customer name is required", 400

        add_customer(name, phone, email, address, session["business_id"])
        return redirect(url_for("customers_page"))

    customers = [dict(customer) for customer in get_all_customers(session["business_id"])]

    for customer in customers:
        customer["invoices"] = get_customer_invoices(customer["name"], session["business_id"])

    return render_template(
        "customers.html",
        customers=customers
    )



@app.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
@login_required
@subscription_required
def edit_customer_page(customer_id):
    customers = get_all_customers(session["business_id"])
    customer = next(
        (c for c in customers if c["id"] == customer_id),
        None
    )

    if customer is None:
        return "Customer not found", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            return "Customer name is required", 400

        success, message = update_customer(
            customer_id, name, phone, email, address, session["business_id"]
        )

        if not success:
            return message, 400

        return redirect(url_for("customers_page"))

    return render_template(
        "edit_customer.html",
        customer=customer
    )



@app.route("/customers/delete/<int:customer_id>", methods=["POST"])
@login_required
@subscription_required
def delete_customer_page(customer_id):
    success, message = delete_customer(customer_id, session["business_id"])

    if not success:
        return message, 400

    return redirect(url_for("customers_page"))




@app.route("/reports")
@login_required
@subscription_required
def reports_page():
    from datetime import date, timedelta

    today = date.today()
    week_start = today - timedelta(days=6)

    daily = get_daily_sales_report(today.isoformat(), session["business_id"])

    weekly = get_weekly_sales_report(
        week_start.isoformat(),
        today.isoformat(),
        session["business_id"]
    )

    monthly = get_monthly_sales_report(
        today.year,
        today.month,
        session["business_id"]
    )

    expenses = get_expense_report(
        week_start.isoformat(),
        today.isoformat(),
        session["business_id"]
    )

    profit = get_profit_report(
        week_start.isoformat(),
        today.isoformat(),
        session["business_id"]
    )

    best_sellers = get_best_selling_products(session["business_id"])

    return render_template(
        "reports.html",
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        expenses=expenses,
        profit=profit,
        best_sellers=best_sellers
    )




@app.route("/settings", methods=["GET", "POST"])
@login_required
@subscription_required
def settings_page():
    if request.method == "POST":
        business_name = request.form.get("business_name", "")
        phone = request.form.get("phone", "")
        email = request.form.get("email", "")
        address = request.form.get("address", "")
        currency = request.form.get("currency", "NGN")

        if currency not in ("NGN", "USD", "GBP", "EUR"):
            return "Invalid currency", 400

        success, message = update_business_settings(
            business_name,
            phone,
            email,
            address,
            currency,
            session["business_id"]
        )

        if not success:
            return message, 400

        return redirect(url_for("settings_page"))

    settings = get_business_settings(session["business_id"])

    return render_template(
        "settings.html",
        settings=settings
    )


if __name__ == "__main__":
    app.run(debug=os.environ.get("ELDEN_ENV") != "production")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")
