"""
routes.py — All Flask route handlers.

Blueprint structure:
  /                    → product landing page
  /checkout/<id>       → checkout form (email capture)
  /pay/<order_id>      → creates Oxapay invoice, redirects to pay link
  /payment/success     → thank-you page
  /payment/cancel      → cancelled page
  /webhooks/oxapay     → Oxapay webhook listener (CRITICAL PATH)
  /order/<order_id>    → order status lookup
"""

import os
import logging
from datetime import datetime

from flask import (
    Blueprint, request, jsonify, render_template,
    redirect, url_for, abort
)

from payments import (
    create_invoice, verify_webhook_signature,
    parse_webhook_payload, generate_order_id
)
from mail_service import send_delivery_email
from database import get_conn

logger = logging.getLogger(__name__)

store_bp = Blueprint("store", __name__)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_product(product_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "SELECT * FROM products WHERE id = %s AND active = TRUE", (product_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _get_order(order_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "SELECT * FROM orders WHERE order_id = %s", (order_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _update_order_status(order_id: str, status: str, track_id: str = None):
    conn = get_conn()
    cur  = conn.cursor()
    if track_id:
        cur.execute(
            "UPDATE orders SET status=%s, track_id=%s, confirmed_at=%s WHERE order_id=%s",
            (status, track_id, datetime.utcnow(), order_id)
        )
    else:
        cur.execute(
            "UPDATE orders SET status=%s WHERE order_id=%s",
            (status, order_id)
        )
    conn.commit()


def _mark_delivery_sent(order_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE orders SET delivery_sent=TRUE WHERE order_id=%s", (order_id,)
    )
    conn.commit()


# ─── Store Routes ─────────────────────────────────────────────────────────────

@store_bp.route("/")
def index():
    """Product landing page — fetch all active products."""
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM products WHERE active=TRUE")
    products = [dict(r) for r in cur.fetchall()]
    return render_template("index.html", products=products)


@store_bp.route("/product/<product_id>")
def product_detail(product_id):
    product = _get_product(product_id)
    if not product:
        abort(404)
    return render_template("product.html", product=product)


@store_bp.route("/checkout/<product_id>", methods=["GET", "POST"])
def checkout(product_id):
    product = _get_product(product_id)
    if not product:
        abort(404)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name  = request.form.get("name", "").strip()

        if not email or "@" not in email:
            return render_template("checkout.html", product=product,
                                   error="Please enter a valid email address.")

        # Create order record
        order_id = generate_order_id()
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO orders (order_id, customer_email, customer_name, product_id, amount_usd)
            VALUES (%s, %s, %s, %s, %s)
        """, (order_id, email, name, product_id, product["price_usd"]))
        conn.commit()

        return redirect(url_for("store.initiate_payment", order_id=order_id))

    return render_template("checkout.html", product=product)


@store_bp.route("/pay/<order_id>")
def initiate_payment(order_id):
    """Create Oxapay invoice and redirect customer to payment page."""
    order = _get_order(order_id)
    if not order:
        abort(404)

    product = _get_product(order["product_id"])
    if not product:
        abort(404)

    base_url = os.environ.get("BASE_URL", request.host_url.rstrip("/"))
    callback_url = f"{base_url}/webhooks/oxapay"
    return_url   = f"{base_url}/payment/success?order_id={order_id}"

    result = create_invoice(
        amount_usd=order["amount_usd"],
        customer_email=order["customer_email"],
        product_name=product["name"],
        order_id=order_id,
        callback_url=callback_url,
        return_url=return_url,
    )

    if not result["success"]:
        logger.error("Invoice creation failed for order %s: %s", order_id, result.get("error"))
        return render_template("error.html", message=result.get("error",
                               "Payment gateway error. Please try again.")), 502

    # Store track_id from Oxapay
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE orders SET track_id=%s, status='awaiting_payment' WHERE order_id=%s",
        (result["track_id"], order_id)
    )
    conn.commit()

    return redirect(result["pay_link"])


@store_bp.route("/payment/success")
def payment_success():
    order_id = request.args.get("order_id", "")
    order    = _get_order(order_id) if order_id else None
    return render_template("success.html", order=order)


@store_bp.route("/payment/cancel")
def payment_cancel():
    return render_template("cancel.html")


@store_bp.route("/order/<order_id>")
def order_status(order_id):
    order = _get_order(order_id)
    if not order:
        abort(404)
    return render_template("order_status.html", order=order)


# ─── Oxapay Webhook — CRITICAL PATH ──────────────────────────────────────────

@store_bp.route("/webhooks/oxapay", methods=["POST"])
def oxapay_webhook():
    """
    Listens for Oxapay payment events.

    Security:
      1. Verify HMAC-SHA512 signature from the 'HMAC' header
      2. Only process 'Confirmed' status events
      3. Idempotency check: skip if delivery already sent

    Automation:
      On Charge:Confirmed → update DB → send product delivery email
    """
    raw_body     = request.get_data()
    received_sig = request.headers.get("HMAC", "")

    # ── Step 1: Verify signature ──────────────────────────────────────────────
    if not verify_webhook_signature(raw_body, received_sig):
        logger.warning("Webhook signature mismatch — possible spoofed request.")
        abort(403)

    # ── Step 2: Parse payload ─────────────────────────────────────────────────
    payload = parse_webhook_payload(raw_body)
    if not payload:
        logger.error("Unparseable webhook payload.")
        return jsonify({"status": "error", "message": "invalid payload"}), 400

    status    = payload.get("status", "")    # e.g. 'Confirmed', 'Waiting', 'Expired'
    order_id  = payload.get("orderId", "")   # matches our internal order_id
    track_id  = str(payload.get("trackId", ""))

    logger.info("Webhook received | status=%s | order=%s | track=%s",
                status, order_id, track_id)

    # ── Step 3: Update order status in DB ────────────────────────────────────
    if order_id:
        _update_order_status(order_id, status.lower(), track_id)

    # ── Step 4: Handle confirmed payment ─────────────────────────────────────
    if status == "Confirmed":
        order = _get_order(order_id)

        if not order:
            logger.error("Webhook: order %s not found in DB.", order_id)
            return jsonify({"status": "error", "message": "order not found"}), 404

        # Idempotency guard: don't send duplicate emails
        if order["delivery_sent"] == 1:
            logger.info("Delivery already sent for order %s — skipping.", order_id)
            return jsonify({"status": "ok", "message": "already delivered"}), 200

        product = _get_product(order["product_id"])
        if not product:
            logger.error("Product %s not found for order %s.", order["product_id"], order_id)
            return jsonify({"status": "error", "message": "product not found"}), 500

        # ── Step 5: Send product delivery email ───────────────────────────────
        sent = send_delivery_email(
            to_email=order["customer_email"],
            customer_name=order["customer_name"] or "",
            product_name=product["name"],
            canva_link=product["canva_link"],
            pdf_link=product.get("pdf_link"),
            order_id=order_id,
        )

        if sent:
            _mark_delivery_sent(order_id)
            logger.info("✓ Product delivered → %s | order %s", order["customer_email"], order_id)
        else:
            logger.error("✗ Delivery email failed for order %s — will need manual resend.", order_id)
            # Still return 200 so Oxapay doesn't retry; handle via admin panel / logs
            return jsonify({"status": "partial", "message": "payment confirmed, email failed"}), 200

    # Oxapay expects a 200 response to stop retrying
    return jsonify({"status": "ok"}), 200


# ─── Register ────────────────────────────────────────────────────────────────

def register_routes(app):
    app.register_blueprint(store_bp)
