# Journey Map Templates — Canva Storefront

Crypto-powered digital product storefront built with Flask + Oxapay.
Designed for Railway deployment.

## Directory Structure

```
canva-store/
├── app.py              # Flask entry point & app factory
├── routes.py           # All URL handlers + webhook listener
├── payments.py         # Oxapay invoice creation & HMAC verification
├── mail_service.py     # SMTP product delivery emails
├── database.py         # SQLite init + helpers
├── templates/
│   ├── index.html      # Product landing page
│   ├── checkout.html   # Email capture form
│   ├── success.html    # Post-payment confirmation
│   ├── cancel.html     # Cancelled payment page
│   └── error.html      # Generic error page
├── static/
│   ├── img/            # Product preview images → add your own here
├── requirements.txt
├── Procfile
├── .env.example
└── .gitignore
```

## Local Setup

```bash
# 1. Clone & enter project
git clone <your-repo> && cd canva-store

# 2. Create virtual environment
python3 -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# → Edit .env with your real keys

# 5. Run
python app.py
```

## Railway Deployment

1. Push repo to GitHub
2. Connect repo in Railway dashboard
3. Add all variables from `.env.example` → Railway Variables tab
4. Railway auto-detects `Procfile` → deploys with gunicorn
5. Set `BASE_URL` to your Railway domain

## Webhook Setup (Oxapay Dashboard)

1. Go to Oxapay → Merchants → your merchant → Webhook
2. Set URL to: `https://YOUR-APP.up.railway.app/webhooks/oxapay`
3. Copy the webhook secret → set as `OXAPAY_WEBHOOK_SECRET` in Railway

## Payment Flow

```
Customer → /checkout/<id>     (email capture)
        → /pay/<order_id>     (creates Oxapay invoice, redirects)
        → Oxapay hosted page  (customer pays crypto)
        → Oxapay webhook POST /webhooks/oxapay
        → HMAC verified ✓
        → DB updated to 'confirmed'
        → Email sent with Canva link
        → Customer inbox ✓
```

## Adding Products

Edit `database.py` → `init_db()` seed block, or insert directly into SQLite:

```sql
INSERT INTO products (id, name, description, price_usd, canva_link, pdf_link)
VALUES ('my-product', 'My Template Pack', 'Description here', 14.99,
        'https://canva.com/your-link', NULL);
```

## ⚠️ Railway SQLite Warning

Railway's filesystem is ephemeral — your SQLite DB resets on redeploy.
For production: add a Railway Volume and set `DB_PATH=/data/store.db`,
or migrate to Railway's Postgres add-on.
