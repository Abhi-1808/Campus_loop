"""Build the local, standalone review edition using the shared frontend."""

import argparse
import base64
import json
import tempfile
from pathlib import Path

from campusloop.app import event_json, now_epoch
from campusloop.config import ROOT, Settings
from campusloop.db import EVENT_QUERY, connect
from campusloop.demo import DEMO_PASSWORD, DEMO_USERS, seed_demo

from .walkthrough import render_walkthrough


def build(output):
    with tempfile.TemporaryDirectory() as temp:
        settings = Settings(Path(temp) / "review.sqlite3", "http://127.0.0.1:8000", False)
        seed_demo(settings)
        with connect(settings.database) as connection:
            rows = connection.execute(f"{EVENT_QUERY} ORDER BY e.starts_at").fetchall()
        fixture = {
            "events": [event_json(row, now_epoch(), private=True) for row in rows],
            "accounts": {role: {"name": name, "email": email, "role": role}
                         for email, name, role in DEMO_USERS},
            "password": DEMO_PASSWORD,
            "timezone": settings.timezone,
            "generated_at": now_epoch() * 1000,
        }

    static = ROOT / "static"
    photo = base64.b64encode((static / "images" / "campus-life.webp").read_bytes()).decode("ascii")
    banner, walkthrough = render_walkthrough(fixture["events"], settings.zone, photo)
    app = (static / "app.js").read_text(encoding="utf-8")
    adapter = (Path(__file__).parent / "adapter.js").read_text(encoding="utf-8")
    data = json.dumps(fixture, ensure_ascii=False).replace("<", "\\u003c")
    document = (static / "index.html").read_text(encoding="utf-8").replace(
        '<link rel="stylesheet" href="/assets/styles.css">',
        f'<style>{(static / "styles.css").read_text(encoding="utf-8")}</style>',
    ).replace(
        '  <script defer src="/assets/app.js"></script>\n', "",
    ).replace(
        '<div id="preview-banner" hidden></div>', banner, 1,
    ).replace(
        '<p class="subtle" role="status">Loading CampusLoop…</p>', walkthrough, 1,
    ).replace(
        "</body>", f"<script>const CAMPUSLOOP_REVIEW_DATA = {data};\n{adapter}\n{app}</script>\n</body>",
    )
    output.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
