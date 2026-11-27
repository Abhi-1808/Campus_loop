"""Fictional, opt-in fixtures for local review."""

from datetime import datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from .db import connect, initialize
from .security import hash_password

DEMO_PASSWORD = "CampusLoop-Demo-2026"
DEMO_USERS = (
    ("student@campusloop.example", "Aarav Sharma", "student"),
    ("organizer@campusloop.example", "Mira Rao", "organizer"),
)
EVENTS = [
    ("Hack the Night", "Technical", "Code Collective", "Innovation Lab", 3, 100, 9,
     "Build a prototype with student developers in a hands-on campus hackathon. Bring an idea or join a team at the kickoff.",
     "Open to all students. Bring a laptop."),
    ("After Hours", "Cultural", "The Arts Society", "Open Air Theatre", 5, 200, 17,
     "An evening of live music, dance, and creative performances by student artists. Doors open thirty minutes before the show.",
     "Open to all students."),
    ("Design Lab: Figma 101", "Workshop", "Design Circle", "Computer Lab 2", 7, 45, 14,
     "A practical introduction to interface design, wireframes, and prototypes. Leave with a small interactive design of your own.",
     "Beginner-friendly. Bring a laptop."),
    ("Campus Cup", "Sports", "Sports Council", "Main Sports Ground", 9, 80, 9,
     "Meet students from other departments at a friendly afternoon of games and teamwork.",
     "All departments welcome. Wear appropriate sports shoes."),
    ("Ideas in Motion", "Academic", "Literary & Debating Society", "Seminar Hall", 11, 65, 11,
     "A student-led discussion and quiz exploring science, culture, and current ideas.",
     "Open to all students."),
    ("Green Campus Drive", "Community", "Eco Club", "Central Lawn", 13, 50, 9,
     "Volunteer at a campus clean-up and tree planting drive. Meet at the lawn for a briefing.",
     "Open to all students. Wear comfortable shoes."),
    ("Robotics Open Lab", "Technical", "Robotics Society", "Engineering Lab", 15, 35, 15,
     "Explore student-built robots and try a short design challenge with the society’s members.",
     "Open to undergraduate and postgraduate students."),
    ("The Campus Open Mic", "Cultural", "The Arts Society", "Black Box Studio", 16, 60, 17,
     "Take the stage or listen to short sets of poetry, storytelling, and acoustic music.",
     "Open to all students."),
    ("Build Your First Portfolio", "Workshop", "Design Circle", "Computer Lab 2", 18, 32, 14,
     "Plan, write, and prototype a portfolio page that tells the story behind one of your projects.",
     "Bring a laptop and one project to showcase."),
    ("Morning Badminton Meet", "Sports", "Sports Council", "Indoor Courts", 20, 40, 8,
     "Join short, friendly doubles matches. The session starts with an open warm-up.",
     "Bring indoor court shoes. All skill levels welcome."),
    ("Research Poster Walk", "Academic", "Student Research Forum", "Academic Atrium", 22, 80, 11,
     "See undergraduate research and ask student presenters about how they investigated their questions.",
     "Open to all students."),
    ("Volunteer Orientation", "Community", "Community Action Club", "Student Centre", 24, 45, 15,
     "Meet the student volunteers behind ongoing campus initiatives and find a project that fits your schedule.",
     "Open to all students."),
]


def seed_demo(settings):
    if settings.production:
        raise RuntimeError("Demo data can only be installed in development.")
    initialize(settings.database)
    today = datetime.now(settings.zone).date()
    credentials = [(email, name, hash_password(DEMO_PASSWORD), role) for email, name, role in DEMO_USERS]
    with connect(settings.database, write=True) as connection:
        connection.executemany(
            """INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO NOTHING""", credentials,
        )
        owner = connection.execute("SELECT id FROM users WHERE email = ?", (DEMO_USERS[1][0],)).fetchone()[0]
        for title, category, club, venue, days, capacity, hour, description, eligibility in EVENTS:
            starts = datetime.combine(today + timedelta(days=days), time(hour), settings.zone)
            closes = starts - timedelta(days=1)
            ends = starts + timedelta(hours=3 if category != "Technical" else 6)
            event_id = uuid5(NAMESPACE_URL, "campusloop.example/events/" + title).hex
            connection.execute(
                """INSERT INTO events (id, owner_id, title, category, organizer, venue, description,
                eligibility, starts_at, ends_at, closes_at, capacity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published') ON CONFLICT(id) DO NOTHING""",
                (event_id, owner, title, category, club, venue, description, eligibility,
                 int(starts.timestamp()), int(ends.timestamp()), int(closes.timestamp()), capacity),
            )
