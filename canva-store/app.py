import os
from flask import Flask
from routes import register_routes
from database import init_db, close_conn

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")

    # Close Postgres connection after each request
    app.teardown_appcontext(close_conn)

    # Register all route blueprints
    register_routes(app)

    # Initialize PostgreSQL schema (idempotent)
    with app.app_context():
        init_db()

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
