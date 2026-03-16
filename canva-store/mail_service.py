"""
mail_service.py — Automated product delivery via email.

Sends the Canva template link + PDF link to the customer
after Oxapay confirms payment.

Env vars required:
  SMTP_HOST      — e.g. smtp.gmail.com  or  smtp.sendgrid.net
  SMTP_PORT      — e.g. 587
  SMTP_USER      — your sending email address
  SMTP_PASSWORD  — app password or SMTP API key
  STORE_NAME     — display name, e.g. "TreatBlocker Templates"
  SUPPORT_EMAIL  — reply-to address
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER      = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD  = os.environ.get("SMTP_PASSWORD", "")
STORE_NAME     = os.environ.get("STORE_NAME", "Journey Map Templates")
SUPPORT_EMAIL  = os.environ.get("SUPPORT_EMAIL", SMTP_USER)


def send_delivery_email(
    to_email: str,
    customer_name: str,
    product_name: str,
    canva_link: str,
    pdf_link: str | None,
    order_id: str
) -> bool:
    """
    Send the purchase confirmation and download/access links.

    Returns True on success, False on failure.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured. Email not sent.")
        return False

    subject = f"🎉 Your {product_name} is ready!"

    html_body = _build_html_email(
        customer_name=customer_name or "there",
        product_name=product_name,
        canva_link=canva_link,
        pdf_link=pdf_link,
        order_id=order_id,
    )
    text_body = _build_text_email(
        customer_name=customer_name or "there",
        product_name=product_name,
        canva_link=canva_link,
        pdf_link=pdf_link,
        order_id=order_id,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"{STORE_NAME} <{SMTP_USER}>"
    msg["To"]       = to_email
    msg["Reply-To"] = SUPPORT_EMAIL

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        logger.info("Delivery email sent → %s | order: %s", to_email, order_id)
        return True

    except smtplib.SMTPException as exc:
        logger.exception("SMTP error sending to %s: %s", to_email, exc)
        return False


# ─── Email Templates ──────────────────────────────────────────────────────────

def _build_html_email(customer_name, product_name, canva_link, pdf_link, order_id):
    pdf_section = ""
    if pdf_link:
        pdf_section = f"""
        <tr>
          <td style="padding:0 0 16px 0;">
            <a href="{pdf_link}"
               style="display:inline-block;background:#1a1a2e;color:#fff;
                      padding:14px 32px;border-radius:8px;text-decoration:none;
                      font-family:'Helvetica Neue',sans-serif;font-size:15px;font-weight:600;">
              ⬇ Download PDF Version
            </a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Helvetica Neue',Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:48px 16px;">
        <table width="560" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;
                      box-shadow:0 4px 24px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);
                       padding:40px 48px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:28px;font-weight:700;
                         letter-spacing:-0.5px;">Payment Confirmed ✓</h1>
              <p style="margin:8px 0 0;color:rgba(255,255,255,0.7);font-size:14px;">
                Order #{order_id}
              </p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:40px 48px;">
              <p style="margin:0 0 24px;color:#374151;font-size:16px;line-height:1.6;">
                Hey <strong>{customer_name}</strong>, your purchase is confirmed!
                Here are your access links for <strong>{product_name}</strong>:
              </p>
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding:0 0 16px 0;">
                    <a href="{canva_link}"
                       style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);
                              color:#fff;padding:14px 32px;border-radius:8px;
                              text-decoration:none;font-size:15px;font-weight:600;">
                      🎨 Open in Canva
                    </a>
                  </td>
                </tr>
                {pdf_section}
              </table>
              <p style="margin:24px 0 0;color:#6b7280;font-size:13px;line-height:1.6;">
                These links are for your personal use only. Save them somewhere safe
                as they may not be re-sent. If you have any issues, reply to this email.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:24px 48px;background:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center;">
                {STORE_NAME} · Questions? Email {SUPPORT_EMAIL}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_text_email(customer_name, product_name, canva_link, pdf_link, order_id):
    pdf_line = f"\nPDF Download: {pdf_link}" if pdf_link else ""
    return f"""Hey {customer_name},

Your payment for {product_name} has been confirmed!

Order ID: {order_id}

ACCESS YOUR TEMPLATES:
Canva Link: {canva_link}{pdf_line}

Please save these links — they are tied to your purchase.
If you need support, reply to this email.

— {STORE_NAME}
"""
