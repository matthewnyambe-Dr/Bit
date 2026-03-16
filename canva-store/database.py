"""
database.py — PostgreSQL connection layer via psycopg2.

Railway provides a managed Postgres instance. Add the "PostgreSQL" plugin
in your Railway project and Railway auto-injects DATABASE_URL into the
environment. No manual configuration needed.

Required env var (auto-set by Railway Postgres plugin):
  DATABASE_URL  — e.g. postgresql://user:pass@host:5432/railway
"""

import os
import logging
import psycopg2
import psycopg2.extras
from flask import g

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Railway sometimes prefixes with 'postgres://' — psycopg2 needs 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# ─── Connection Management ────────────────────────────────────────────────────

def get_conn():
    """
    Open a per-request psycopg2 connection stored on Flask's `g` object.
    Rows are returned as dicts via RealDictCursor.
    """
    if "pg_conn" not in g:
        g.pg_conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return g.pg_conn


def close_conn(e=None):
    """Teardown: close the connection at the end of each request."""
    conn = g.pop("pg_conn", None)
    if conn is not None:
        conn.close()


def _raw_conn():
    """
    Open a standalone connection used only during init_db at startup,
    outside a request context.
    """
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


# ─── Schema Init ─────────────────────────────────────────────────────────────

def init_db():
    """
    Create tables and seed products. Safe to call on every deploy —
    uses IF NOT EXISTS / ON CONFLICT DO NOTHING so it's fully idempotent.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add the Railway PostgreSQL plugin to your project."
        )

    conn = _raw_conn()
    cur  = conn.cursor()

    # ── Orders ────────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              SERIAL          PRIMARY KEY,
            order_id        TEXT            NOT NULL UNIQUE,
            track_id        TEXT,
            customer_email  TEXT            NOT NULL,
            customer_name   TEXT,
            product_id      TEXT            NOT NULL,
            amount_usd      NUMERIC(10, 2)  NOT NULL,
            currency        TEXT            DEFAULT 'USDT',
            status          TEXT            DEFAULT 'pending',
            delivery_sent   BOOLEAN         DEFAULT FALSE,
            created_at      TIMESTAMPTZ     DEFAULT NOW(),
            confirmed_at    TIMESTAMPTZ
        )
    """)

    # ── Products ──────────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          TEXT            PRIMARY KEY,
            name        TEXT            NOT NULL,
            description TEXT,
            price_usd   NUMERIC(10, 2)  NOT NULL,
            canva_link  TEXT            NOT NULL,
            pdf_link    TEXT,
            preview_img TEXT,
            active      BOOLEAN         DEFAULT TRUE
        )
    """)

    # ── Seed products (idempotent) ────────────────────────────────────────────
    cur.execute("""
        INSERT INTO products (id, name, description, price_usd, canva_link, pdf_link, preview_img)
        VALUES
        (
            'journey-map-pro',
            'Journey Map Pro Bundle',
            '12 premium customer journey map infographic templates. Fully editable in Canva. Perfect for UX presentations, startup pitches, and marketing decks.',
            9.99,
            'https://www.canva.com/templates/your-link-here',
            'https://your-cdn.com/journey-map-pro.pdf',
            '/static/img/preview-journey-map.jpg'
        ),
        (
            'journey-map-starter',
            'Journey Map Starter Pack',
            '4 essential journey map templates for freelancers and solo founders. Clean, minimal, conversion-focused.',
            4.99,
            'https://www.canva.com/templates/your-starter-link',
            NULL,
            '/static/img/preview-starter.jpg'
        )
        ON CONFLICT (id) DO NOTHING
    """)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("[DB] PostgreSQL initialized successfully.")
    print("[DB] PostgreSQL initialized successfully.")
