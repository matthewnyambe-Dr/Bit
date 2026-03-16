"""
payments.py — Oxapay crypto payment integration.

Handles:
  - Creating a payment invoice via Oxapay's /payment endpoint
  - Verifying incoming webhook HMAC signatures
  - Parsing webhook event payloads

Env vars required:
  OXAPAY_MERCHANT_KEY   — your Oxapay merchant API key
  OXAPAY_WEBHOOK_SECRET — the webhook secret set in your Oxapay dashboard
"""

import os
import hmac
import hashlib
import json
import uuid
import requests
import logging

logger = logging.getLogger(__name__)

OXAPAY_API_BASE       = "https://api.oxapay.com"
OXAPAY_MERCHANT_KEY   = os.environ.get("OXAPAY_MERCHANT_KEY", "")
OXAPAY_WEBHOOK_SECRET = os.environ.get("OXAPAY_WEBHOOK_SECRET", "")


# ─── Invoice Creation ────────────────────────────────────────────────────────

def create_invoice(amount_usd: float, customer_email: str, product_name: str,
                   order_id: str, callback_url: str, return_url: str) -> dict:
    """
    Create an Oxapay payment invoice.

    Returns a dict with keys:
      success   (bool)
      track_id  (str)   — Oxapay's internal tracking ID
      pay_link  (str)   — URL to redirect customer to
      error     (str)   — populated on failure
    """
    if not OXAPAY_MERCHANT_KEY:
        logger.error("OXAPAY_MERCHANT_KEY is not set.")
        return {"success": False, "error": "Payment gateway not configured."}

    payload = {
        "merchant":    OXAPAY_MERCHANT_KEY,
        "amount":      amount_usd,
        "currency":    "USD",
        "life_time":   30,               # invoice expires in 30 minutes
        "fee_paid_by_payer": 0,          # merchant absorbs network fee
        "under_paid_cover":  2,          # allow up to 2% underpayment
        "callback_url": callback_url,
        "return_url":   return_url,
        "order_id":     order_id,
        "description":  f"Purchase: {product_name}",
        "email":        customer_email,
    }

    try:
        resp = requests.post(
            f"{OXAPAY_API_BASE}/merchants/request",
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        # Oxapay returns result=100 on success
        if data.get("result") == 100:
            return {
                "success":  True,
                "track_id": str(data.get("trackId", "")),
                "pay_link": data.get("payLink", ""),
            }
        else:
            msg = data.get("message", "Unknown Oxapay error")
            logger.error("Oxapay invoice error: %s | payload: %s", msg, data)
            return {"success": False, "error": msg}

    except requests.RequestException as exc:
        logger.exception("Network error creating Oxapay invoice: %s", exc)
        return {"success": False, "error": "Could not reach payment gateway. Try again."}


# ─── Webhook Signature Verification ──────────────────────────────────────────

def verify_webhook_signature(raw_body: bytes, received_sig: str) -> bool:
    """
    Verify that the webhook POST came from Oxapay using HMAC-SHA512.

    Oxapay sends the signature in the 'HMAC' header.
    The signature is: HMAC-SHA512(raw_body_bytes, OXAPAY_WEBHOOK_SECRET)
    """
    if not OXAPAY_WEBHOOK_SECRET:
        logger.warning("OXAPAY_WEBHOOK_SECRET not set — skipping signature check (INSECURE).")
        return True  # fail open during local dev; tighten in prod

    expected = hmac.new(
        OXAPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(expected.lower(), received_sig.lower())


# ─── Payload Parsing ──────────────────────────────────────────────────────────

def parse_webhook_payload(raw_body: bytes) -> dict | None:
    """
    Safely parse the webhook JSON body.

    Expected fields from Oxapay:
      status    — 'Waiting' | 'Confirming' | 'Confirmed' | 'Expired' | etc.
      trackId   — Oxapay tracking ID
      orderId   — your order_id passed during invoice creation
      amount    — amount received
      currency  — e.g. 'USDT'
      type      — 'Payment'
    """
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
        return None


# ─── Order ID Generator ───────────────────────────────────────────────────────

def generate_order_id() -> str:
    """Generate a collision-resistant order ID."""
    return f"ORD-{uuid.uuid4().hex[:12].upper()}"
