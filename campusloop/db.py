import os
import sqlite3
from contextlib import contextmanager

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'organizer')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires INTEGER NOT NULL
);
CREATE INDEX sessions_expiry ON sessions(expires);
CREATE TABLE login_attempts (
    scope TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    resets_at INTEGER NOT NULL
);
CREATE INDEX login_attempts_expiry ON login_attempts(resets_at);
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'Technical', 'Cultural', 'Workshop', 'Sports', 'Academic', 'Community'
    )),
    organizer TEXT NOT NULL,
    venue TEXT NOT NULL,
    description TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    starts_at INTEGER NOT NULL,
    ends_at INTEGER NOT NULL,
    closes_at INTEGER NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity BETWEEN 1 AND 5000),
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'cancelled', 'archived')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (starts_at < ends_at),
    CHECK (closes_at <= starts_at)
);
CREATE INDEX events_listing ON events(status, starts_at, id);
CREATE INDEX events_organizer ON events(owner_id, starts_at, id);
CREATE TABLE registrations (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    student_id INTEGER NOT NULL REFERENCES users(id),
    department TEXT NOT NULL,
    year TEXT NOT NULL CHECK (year IN ('1', '2', '3', '4', 'PG', 'Other')),
    registered_at INTEGER NOT NULL,
    cancelled_at INTEGER,
    UNIQUE (event_id, student_id)
);
CREATE INDEX registrations_attendees ON registrations(event_id, cancelled_at);
CREATE INDEX registrations_student ON registrations(student_id, registered_at);
"""

EVENT_QUERY = """
SELECT e.*, (SELECT COUNT(*) FROM registrations r
    WHERE r.event_id = e.id AND r.cancelled_at IS NULL) AS registrations
FROM events AS e
"""


@contextmanager
def connect(path, *, write=False):
    connection = sqlite3.connect(path, timeout=8, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.create_function("casefold", 1, str.casefold, deterministic=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        if write:
            connection.commit()
    except BaseException:
        if write and connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    with connect(path, write=True) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise RuntimeError(f"Unsupported database schema {version}.")
        for statement in SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def event_by_id(connection, event_id):
    return connection.execute(f"{EVENT_QUERY} WHERE e.id = ?", (event_id,)).fetchone()


def backup(source, destination):
    if destination.exists():
        raise FileExistsError(f"Backup already exists: {destination}")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with connect(source) as live, connect(destination) as copy:
            live.backup(copy)
            copy.execute("PRAGMA secure_delete = ON")
            copy.execute("BEGIN IMMEDIATE")
            copy.execute("DELETE FROM sessions")
            copy.execute("DELETE FROM login_attempts")
            copy.commit()
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup failed the SQLite integrity check.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
