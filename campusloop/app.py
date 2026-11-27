import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import ROOT, Settings
from .db import EVENT_QUERY, connect, event_by_id, initialize
from .demo import DEMO_USERS
from .models import CATEGORIES, EventForm, Login, RegistrationCancellation, RegistrationForm, Revision
from .security import (
    SESSION_LIFETIME, complete_login_attempt, digest_token, hash_password, normalize_email, reserve_login_attempt,
    session_user, start_session, verify_password,
)

LOGGER = logging.getLogger(__name__)
MAX_BODY = 16_384
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'"
)
EVENT_FIELDS = (
    "id", "title", "category", "organizer", "venue", "description", "eligibility", "capacity", "status",
)
EVENT_UPDATE = """
title = ?, category = ?, organizer = ?, venue = ?, description = ?, eligibility = ?,
starts_at = ?, ends_at = ?, closes_at = ?, capacity = ?, status = ?
"""
PUBLIC_STATUS = {
    "cancelled": "Cancelled", "draft": "Draft", "archived": "Archived",
    "open": "Open", "full": "Full", "closed": "Registration closed",
    "ongoing": "In progress", "completed": "Completed",
}


def now_epoch():
    return int(time.time())


def iso(value):
    return datetime.fromtimestamp(value, UTC).isoformat() if value is not None else None


def availability(event, current_time):
    status = event["status"]
    if status != "published":
        return status
    if event["ends_at"] <= current_time:
        return "completed"
    if event["starts_at"] <= current_time:
        return "ongoing"
    if event["closes_at"] <= current_time:
        return "closed"
    if event["registrations"] >= event["capacity"]:
        return "full"
    return "open"


def event_json(event, current_time, *, private=False):
    state = availability(event, current_time)
    body = {key: event[key] for key in EVENT_FIELDS}
    body.update({key: iso(event[key]) for key in ("starts_at", "ends_at", "closes_at")})
    body.update(state=state, state_label=PUBLIC_STATUS[state],
                seats_left=max(event["capacity"] - event["registrations"], 0))
    if private:
        body.update(version=event["version"], registrations=event["registrations"])
    return body


def registration_json(row):
    return {
        "id": row["id"], "event_id": row["event_id"], "department": row["department"],
        "year": row["year"], "registered_at": iso(row["registered_at"]),
        "cancelled_at": iso(row["cancelled_at"]),
    }


def visible_event(connection, event_id, user):
    event = event_by_id(connection, event_id)
    if event is None:
        raise HTTPException(404, "Event not found.")
    if event["status"] in {"published", "cancelled"}:
        return event
    if user and event["owner_id"] == user["id"]:
        return event
    if user and event["status"] == "archived" and student_registration(connection, event_id, user["id"]):
        return event
    raise HTTPException(404, "Event not found.")


def student_registration(connection, event_id, student_id):
    return connection.execute(
        "SELECT * FROM registrations WHERE event_id = ? AND student_id = ?", (event_id, student_id)
    ).fetchone()


def owned_event(connection, event_id, organizer, *, allow_archived=False):
    event = event_by_id(connection, event_id)
    if not event or event["owner_id"] != organizer["id"]:
        raise HTTPException(404, "Event not found.")
    if not allow_archived and event["status"] == "archived":
        raise HTTPException(409, "This event is archived.")
    return event


def check_revision(event, expected):
    if event["version"] != expected:
        raise HTTPException(409, "This event changed. Reopen it before saving.")


def check_publication(form, values, *, previous=None):
    if form.status == "published" and (previous is None or previous["status"] == "draft"):
        if values[8] <= now_epoch():
            raise HTTPException(422, "Set a future registration deadline to publish this event.")


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        initialize(settings.database)
        if settings.production:
            with connect(settings.database) as connection:
                demo_accounts = connection.execute(
                    "SELECT 1 FROM users WHERE email IN (?, ?) LIMIT 1",
                    tuple(account[0] for account in DEMO_USERS),
                ).fetchone()
            if demo_accounts:
                raise RuntimeError("Production cannot use a database containing local review accounts.")
        application.state.dummy_hash = hash_password("nonexistent CampusLoop user")
        yield

    app = FastAPI(title="CampusLoop", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    allowed_hosts = [settings.host] if settings.production else list({settings.host, "localhost", "127.0.0.1"})
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts, www_redirect=False)
    app.mount("/assets", StaticFiles(directory=ROOT / "static"), name="assets")

    @app.middleware("http")
    async def request_policy(request: Request, call_next):
        is_api = request.url.path.startswith("/api/")
        if is_api and request.method not in {"GET", "HEAD", "OPTIONS"}:
            error = None
            request_origin = request.headers.get("origin")
            if request_origin != settings.origin or request.headers.get("x-campusloop-request") != "1":
                error = (403, "This request could not be verified. Reload the page and try again.")
            elif request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                error = (415, "Send a JSON request.")
            else:
                content_length = request.headers.get("content-length", "")
                if not content_length.isascii() or not content_length.isdigit() or len(content_length) > 6 or int(content_length) > MAX_BODY:
                    error = (413, "The request is too large.")
            if not error:
                response = await call_next(request)
            else:
                response = JSONResponse({"detail": error[1]}, status_code=error[0])
        else:
            response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if is_api or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc):
        fields = {}
        for issue in exc.errors():
            label = str(issue["loc"][-1]).replace("_", " ").capitalize()
            message = issue["msg"].removeprefix("Value error, ")
            fields[label] = message
        return JSONResponse(
            {"detail": "Check the form details and try again.", "fields": fields},
            status_code=422,
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def database_unavailable(_request, exc):
        LOGGER.error("Database operation failed", exc_info=exc)
        return JSONResponse({"detail": "CampusLoop is temporarily unavailable."}, status_code=503)

    def current_user(request: Request):
        return session_user(settings.database, request.cookies.get(settings.cookie_name))

    def require_student(user=Depends(current_user)):
        if not user:
            raise HTTPException(401, "Sign in to continue.")
        if user["role"] != "student":
            raise HTTPException(403, "A student account is required.")
        return user

    def require_organizer(user=Depends(current_user)):
        if not user:
            raise HTTPException(401, "Sign in to continue.")
        if user["role"] != "organizer":
            raise HTTPException(403, "An organizer account is required.")
        return user

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static" / "index.html", media_type="text/html")

    @app.get("/healthz")
    def health():
        with connect(settings.database) as connection:
            connection.execute("SELECT id FROM users LIMIT 1").fetchone()
        return {"status": "ok"}

    @app.get("/api/session")
    def session(user=Depends(current_user)):
        return {"user": dict(user) if user else None, "timezone": settings.timezone}

    @app.post("/api/session")
    def log_in(request: Request, response: Response, form: Login):
        try:
            email = normalize_email(form.email)
        except ValueError:
            email = form.email.strip().casefold()
        ip = request.client.host if request.client else "unknown"
        with connect(settings.database, write=True) as connection:
            retry_after, ip_resets_at = reserve_login_attempt(connection, email, ip)
            user = connection.execute(
                "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
            ).fetchone()
        if retry_after:
            raise HTTPException(429, "Try again in a few minutes.", headers={"Retry-After": str(retry_after)})
        stored = user["password_hash"] if user else request.app.state.dummy_hash
        valid = verify_password(form.password, stored)
        if not user or not valid:
            raise HTTPException(401, "The email or password is incorrect.")
        with connect(settings.database, write=True) as connection:
            live = connection.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user["id"],)).fetchone()
            if not live or live["password_hash"] != stored:
                raise HTTPException(401, "The email or password is incorrect.")
            complete_login_attempt(connection, email, ip, ip_resets_at)
            role_matches = not form.role or live["role"] == form.role
            if role_matches:
                token = start_session(connection, user["id"], request.cookies.get(settings.cookie_name))
        if not role_matches:
            raise HTTPException(403, "This account belongs to the other sign-in. Switch sign-in and try again.")
        response.set_cookie(
            settings.cookie_name, token, max_age=SESSION_LIFETIME, secure=settings.production,
            httponly=True, samesite="lax", path="/",
        )
        return {"user": {key: live[key] for key in ("id", "email", "name", "role")}}

    @app.delete("/api/session")
    def log_out(request: Request, response: Response):
        token = request.cookies.get(settings.cookie_name)
        if token and len(token) == 43:
            with connect(settings.database, write=True) as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (digest_token(token),))
        response.delete_cookie(
            settings.cookie_name, path="/", secure=settings.production, httponly=True, samesite="lax"
        )
        return {"user": None}

    @app.get("/api/events")
    def events(
        q: Annotated[str, Query(max_length=120)] = "",
        category: Annotated[str, Query(max_length=20)] = "",
        status: Annotated[str, Query(pattern="^(upcoming|open|past|all)$")] = "upcoming",
        order: Annotated[str, Query(pattern="^(soon|latest|deadline)$")] = "soon",
        page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    ):
        if category and category not in CATEGORIES:
            raise HTTPException(422, "Choose a valid event category.")
        current_time = now_epoch()
        where = ["e.status IN ('published', 'cancelled')"]
        parameters = []
        if q.strip():
            keyword = q.strip().casefold()
            where.append("instr(casefold(e.title || ' ' || e.organizer || ' ' || e.venue || ' ' || e.description), ?) > 0")
            parameters.append(keyword)
        if category:
            where.append("e.category = ?")
            parameters.append(category)
        if status == "upcoming":
            where.append("e.ends_at > ? AND e.status = 'published'")
            parameters.append(current_time)
        elif status == "past":
            where.append("(e.ends_at <= ? OR e.status = 'cancelled')")
            parameters.append(current_time)
        elif status == "open":
            where.append("""e.closes_at > ? AND e.status = 'published' AND e.capacity >
                (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.cancelled_at IS NULL)""")
            parameters.append(current_time)
        clause = " AND ".join(where)
        ordering = {"soon": "e.starts_at, e.id", "latest": "e.starts_at DESC, e.id",
                    "deadline": "e.closes_at, e.starts_at, e.id"}[order]
        page_size = 12
        with connect(settings.database) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                f"SELECT COUNT(*) FROM events e WHERE {clause}", parameters
            ).fetchone()[0]
            items = connection.execute(
                f"{EVENT_QUERY} WHERE {clause} ORDER BY {ordering} LIMIT ? OFFSET ?",
                (*parameters, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"events": [event_json(item, current_time) for item in items],
                "page": page, "pages": max(1, (total + page_size - 1) // page_size), "total": total}

    @app.get("/api/events/{event_id}")
    def detail(event_id: str, user=Depends(current_user)):
        with connect(settings.database) as connection:
            event = visible_event(connection, event_id, user)
            registration = student_registration(connection, event_id, user["id"]) if user else None
        return {"event": event_json(event, now_epoch()),
                "registration": registration_json(registration) if registration else None}

    @app.post("/api/events/{event_id}/registration", status_code=201)
    def register(event_id: str, form: RegistrationForm, user=Depends(require_student)):
        with connect(settings.database, write=True) as connection:
            event = visible_event(connection, event_id, user)
            current_time = now_epoch()
            prior = student_registration(connection, event_id, user["id"])
            if prior and prior["cancelled_at"] is None:
                raise HTTPException(409, "You already have a registration for this event.")
            if availability(event, current_time) != "open":
                raise HTTPException(409, "Registration is no longer available for this event.")
            registration_id = uuid4().hex
            if prior:
                connection.execute(
                    """UPDATE registrations SET id = ?, department = ?, year = ?, registered_at = ?,
                    cancelled_at = NULL WHERE id = ?""",
                    (registration_id, form.department, form.year, current_time, prior["id"]),
                )
            else:
                connection.execute(
                    "INSERT INTO registrations VALUES (?, ?, ?, ?, ?, ?, NULL)",
                    (registration_id, event_id, user["id"], form.department, form.year, current_time),
                )
            registration = student_registration(connection, event_id, user["id"])
        return {"registration": registration_json(registration)}

    @app.delete("/api/events/{event_id}/registration")
    def cancel_registration(event_id: str, form: RegistrationCancellation | None = None,
                            user=Depends(require_student)):
        with connect(settings.database, write=True) as connection:
            event = visible_event(connection, event_id, user)
            registration = student_registration(connection, event_id, user["id"])
            if not registration:
                raise HTTPException(404, "Registration not found.")
            if form and form.registration_id and registration["id"] != form.registration_id:
                raise HTTPException(409, "This registration changed. Reopen My events before cancelling.")
            current_time = now_epoch()
            if registration["cancelled_at"] is not None:
                return {"cancelled": True}
            if event["starts_at"] <= current_time:
                raise HTTPException(409, "Registration cannot be cancelled after the event starts.")
            connection.execute("UPDATE registrations SET cancelled_at = ? WHERE id = ?",
                               (current_time, registration["id"]))
        return {"cancelled": True}

    @app.get("/api/my-events")
    def my_events(user=Depends(require_student)):
        current_time = now_epoch()
        with connect(settings.database) as connection:
            rows = connection.execute(
                """SELECT e.*, r.event_id, r.department, r.year, r.registered_at, r.cancelled_at,
                r.id AS registration_id, (SELECT COUNT(*) FROM registrations ar
                    WHERE ar.event_id = e.id AND ar.cancelled_at IS NULL) AS registrations
                FROM events e JOIN registrations r ON r.event_id = e.id WHERE r.student_id = ?
                ORDER BY (e.starts_at <= ? OR r.cancelled_at IS NOT NULL OR e.status IN ('cancelled', 'archived')),
                CASE WHEN e.starts_at > ? AND r.cancelled_at IS NULL THEN e.starts_at ELSE -e.starts_at END""",
                (user["id"], current_time, current_time),
            ).fetchall()
        return {"items": [{"event": event_json(row, current_time),
                           "registration": {**registration_json(row), "id": row["registration_id"]}}
                          for row in rows]}

    @app.get("/api/organizer/events")
    def organizer_events(user=Depends(require_organizer)):
        with connect(settings.database) as connection:
            rows = connection.execute(
                f"{EVENT_QUERY} WHERE e.owner_id = ? ORDER BY (e.status = 'archived'), e.starts_at DESC, e.id",
                (user["id"],),
            ).fetchall()
        return {"events": [event_json(row, now_epoch(), private=True) for row in rows]}

    @app.get("/api/organizer/events/{event_id}")
    def organizer_event(event_id: str, user=Depends(require_organizer)):
        with connect(settings.database) as connection:
            event = owned_event(connection, event_id, user, allow_archived=True)
        return {"event": event_json(event, now_epoch(), private=True)}

    @app.post("/api/organizer/events", status_code=201)
    def create_event(form: EventForm, user=Depends(require_organizer)):
        values = form.database_values(settings.zone)
        event_id = uuid4().hex
        with connect(settings.database, write=True) as connection:
            check_publication(form, values)
            connection.execute(
                """INSERT INTO events (id, owner_id, title, category, organizer, venue,
                description, eligibility, starts_at, ends_at, closes_at, capacity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (event_id, user["id"], *values)
            )
            event = event_by_id(connection, event_id)
        return {"event": event_json(event, now_epoch(), private=True)}

    @app.put("/api/organizer/events/{event_id}")
    def update_event(event_id: str, form: EventForm, user=Depends(require_organizer)):
        values = form.database_values(settings.zone)
        with connect(settings.database, write=True) as connection:
            event = owned_event(connection, event_id, user)
            check_revision(event, form.version)
            current_time = now_epoch()
            if event["status"] == "cancelled" or (event["status"] == "published" and event["starts_at"] <= current_time):
                raise HTTPException(409, "Cancelled events and events that have already started are read-only.")
            if event["status"] == "published" and form.status == "draft":
                raise HTTPException(409, "Cancel the event to remove it from upcoming listings.")
            if form.capacity < event["registrations"]:
                raise HTTPException(409, "Capacity cannot be lower than active registrations.")
            if form.status == "published" and values[6] <= current_time:
                raise HTTPException(422, "The event start time must be in the future.")
            check_publication(form, values, previous=event)
            connection.execute(
                f"UPDATE events SET {EVENT_UPDATE}, version = version + 1 WHERE id = ?", (*values, event_id)
            )
            updated = event_by_id(connection, event_id)
        return {"event": event_json(updated, now_epoch(), private=True)}

    @app.post("/api/organizer/events/{event_id}/cancel")
    def cancel_event(event_id: str, form: Revision, user=Depends(require_organizer)):
        with connect(settings.database, write=True) as connection:
            event = owned_event(connection, event_id, user)
            check_revision(event, form.version)
            if event["status"] != "published" or event["starts_at"] <= now_epoch():
                raise HTTPException(409, "Only a published event that has not started can be cancelled.")
            connection.execute("UPDATE events SET status = 'cancelled', version = version + 1 WHERE id = ?",
                               (event_id,))
        return {"cancelled": True}

    @app.delete("/api/organizer/events/{event_id}")
    def archive_event(event_id: str, form: Revision, user=Depends(require_organizer)):
        with connect(settings.database, write=True) as connection:
            event = owned_event(connection, event_id, user, allow_archived=True)
            if event["status"] == "archived":
                return {"archived": True}
            check_revision(event, form.version)
            if event["status"] == "published" and event["ends_at"] > now_epoch():
                raise HTTPException(409, "Cancel this event before removing it from listings.")
            connection.execute("UPDATE events SET status = 'archived', version = version + 1 WHERE id = ?",
                               (event_id,))
        return {"archived": True}

    @app.get("/api/organizer/events/{event_id}/attendees")
    def attendees(event_id: str, user=Depends(require_organizer)):
        with connect(settings.database) as connection:
            event = owned_event(connection, event_id, user, allow_archived=True)
            rows = connection.execute(
                """SELECT u.name, u.email, r.* FROM registrations r JOIN users u ON u.id = r.student_id
                WHERE r.event_id = ? ORDER BY (r.cancelled_at IS NOT NULL), r.registered_at, r.id""", (event_id,)
            ).fetchall()
        return {"event": event_json(event, now_epoch(), private=True),
                "items": [{**registration_json(row), "name": row["name"], "email": row["email"]} for row in rows]}

    return app
