import os

import config  # noqa: F401
import db
import security

SEEDS = [  # (slug, name, url, auth_type, secret)
    ("woocommerce", "WooCommerce store", os.getenv("SEED_WOOCOMMERCE_URL"), "none", None),
    ("notes", "Notes", os.getenv("SEED_NOTES_URL"), "none", None),
    ("utilities", "Utilities", os.getenv("SEED_UTILITIES_URL"), "bearer", os.getenv("SEED_UTILITIES_TOKEN")),
]


def run() -> None:
    db.init_db()
    if not db.one("SELECT 1 AS x FROM users LIMIT 1"):
        db.execute(
            "INSERT INTO users(email, name, role, password_hash, created_at) VALUES (?,?,?,?,?)",
            (os.environ["GATEWAY_ADMIN_EMAIL"].lower(), "Admin", "admin",
             security.hash_password(os.environ["GATEWAY_ADMIN_PASSWORD"]), db.now()),
        )
    if not db.one("SELECT 1 AS x FROM servers LIMIT 1"):
        for slug, name, url, auth_type, secret in SEEDS:
            if url:
                db.execute(
                    "INSERT INTO servers(slug, name, url, auth_type, credential_enc, created_at) VALUES (?,?,?,?,?,?)",
                    (slug, name, url, auth_type, security.encrypt(secret) if secret else None, db.now()),
                )