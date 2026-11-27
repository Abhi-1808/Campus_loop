import hashlib
import hmac
import re
import secrets
import threading
import time

from .db import connect

SESSION_LIFETIME = 60 * 60 * 10
WINDOW = 15 * 60
PASSWORD_WORKERS = threading.BoundedSemaphore(4)
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def normalize_email(value):
    email = value.strip().casefold()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def hash_password(password, salt=None):
    salt = salt if salt is not None else secrets.token_bytes(16)
    with PASSWORD_WORKERS:
        digest = hashlib.scrypt(
            password.encode(), salt=salt, n=2**15, r=8, p=3, dklen=32, maxmem=64 * 1024 * 1024
        )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password, stored):
    salt = bytes.fromhex(stored.split(":", 1)[0])
    return hmac.compare_digest(hash_password(password, salt), stored)


def digest_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(connection, user_id, old_token):
    current_time = int(time.time())
    token = secrets.token_urlsafe(32)
    connection.execute("DELETE FROM sessions WHERE expires <= ?", (current_time,))
    if old_token:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (digest_token(old_token),))
    connection.execute(
        "INSERT INTO sessions VALUES (?, ?, ?)",
        (digest_token(token), user_id, current_time + SESSION_LIFETIME),
    )
    return token


def session_user(path, token):
    if not token or len(token) != 43:
        return None
    with connect(path) as connection:
        return connection.execute(
            """SELECT u.id, u.email, u.name, u.role
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires > ? AND u.active = 1""",
            (digest_token(token), int(time.time())),
        ).fetchone()


def reserve_login_attempt(connection, email, ip):
    current_time = int(time.time())
    connection.execute("DELETE FROM login_attempts WHERE resets_at <= ?", (current_time,))
    ip_scope = f"ip:{digest_token(ip)}"
    scopes = [(f"account:{digest_token(email)}", 8), (ip_scope, 100)]
    ip_resets_at = current_time + WINDOW
    for scope, limit in scopes:
        existing = connection.execute(
            "SELECT attempts, resets_at FROM login_attempts WHERE scope = ?", (scope,)
        ).fetchone()
        if existing and existing["attempts"] >= limit:
            return existing["resets_at"] - current_time, None
        if existing and scope == ip_scope:
            ip_resets_at = existing["resets_at"]
    for scope, _ in scopes:
        connection.execute(
            """INSERT INTO login_attempts VALUES (?, 1, ?)
            ON CONFLICT(scope) DO UPDATE SET attempts = attempts + 1""",
            (scope, current_time + WINDOW),
        )
    return 0, ip_resets_at


def complete_login_attempt(connection, email, ip, ip_resets_at):
    """Clear account failures and release this successful IP reservation."""
    connection.execute("DELETE FROM login_attempts WHERE scope = ?", (f"account:{digest_token(email)}",))
    connection.execute(
        """UPDATE login_attempts SET attempts = attempts - 1
        WHERE scope = ? AND resets_at = ? AND attempts > 0""",
        (f"ip:{digest_token(ip)}", ip_resets_at),
    )
