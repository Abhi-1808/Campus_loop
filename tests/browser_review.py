"""Optional Chromium smoke checks for the real app and the standalone review file."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from playwright.sync_api import expect, sync_playwright

from campusloop.demo import DEMO_PASSWORD, DEMO_USERS

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8147"


def ready(process):
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("The CampusLoop server exited.")
        try:
            with urlopen(ORIGIN + "/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.15)
    raise RuntimeError("CampusLoop didn't start in time.")


def sign_in(page, email, button="Sign in"):
    page.get_by_label("Email address").fill(email)
    page.get_by_label("Password").fill(DEMO_PASSWORD)
    page.get_by_role("button", name=button, exact=True).click()


def wait_for_heading(page, title):
    expect(page.get_by_role("heading", name=title, level=1)).to_be_visible()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium")
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporary:
        portable = {"CAMPUSLOOP_ENV": "development", "CAMPUSLOOP_ORIGIN": ORIGIN,
                    "CAMPUSLOOP_DB": str(Path(temporary) / "test.sqlite3")}
        env = {**os.environ, **portable}
        subprocess.run([sys.executable, "-m", "campusloop", "seed-demo"], cwd=ROOT, env=env,
                       check=True, stdout=subprocess.DEVNULL)
        with subprocess.Popen([sys.executable, "-m", "campusloop", "serve", "--port", "8147"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL) as server:
            try:
                ready(server)
                exercise(args)
            finally:
                server.terminate()
                server.wait(timeout=8)


def exercise(args):
    errors = []
    with sync_playwright() as engine:
        launch = {"headless": True, "args": ["--no-sandbox"]}
        if args.chromium:
            launch["executable_path"] = args.chromium
        browser = engine.chromium.launch(**launch)
        student = browser.new_page(viewport={"width": 1440, "height": 1000})
        student.on("pageerror", lambda error: errors.append(str(error)))
        student.goto(ORIGIN)
        wait_for_heading(student, "Good things happen here.")
        expect(student.locator(".hero-media img")).to_be_visible()
        assert student.locator(".hero-media img").evaluate("img => img.complete && img.naturalWidth > 0")
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            student.screenshot(path=args.screenshots / "campusloop-home.png", full_page=True)
        student.keyboard.press("Tab")
        expect(student.get_by_role("link", name="Skip to content")).to_be_focused()
        student.keyboard.press("Enter")
        expect(student.get_by_role("main")).to_be_focused()

        student.get_by_role("link", name="Explore events", exact=True).click()
        wait_for_heading(student, "Explore events")
        student.get_by_label("Search events").fill("design lab")
        student.get_by_role("combobox", name="Category", exact=True).select_option("Workshop")
        student.get_by_role("button", name="Apply filters").click()
        expect(student.get_by_text("1 event", exact=True)).to_be_visible()
        student.get_by_role("link", name="Design Lab: Figma 101", exact=False).click()
        wait_for_heading(student, "Design Lab: Figma 101")
        student.get_by_role("link", name="Sign in to register").click()
        wait_for_heading(student, "Student sign-in")
        sign_in(student, DEMO_USERS[0][0])
        wait_for_heading(student, "Register for event")
        student.get_by_label("Department").fill("Computer Science")
        student.get_by_role("combobox", name="Year", exact=True).select_option("2")
        student.get_by_role("button", name="Confirm registration").click()
        wait_for_heading(student, "My events")
        expect(student.get_by_text("Your registration is confirmed.")).to_be_visible()
        student.reload()
        wait_for_heading(student, "My events")
        expect(student.get_by_role("link", name="Design Lab: Figma 101")).to_be_visible()

        organizer = browser.new_page(viewport={"width": 1024, "height": 760})
        organizer.on("pageerror", lambda error: errors.append(str(error)))
        organizer.goto(ORIGIN + "/#login")
        organizer.get_by_role("link", name="Organisation sign-in", exact=True).click()
        wait_for_heading(organizer, "Organisation sign-in")
        sign_in(organizer, DEMO_USERS[1][0])
        wait_for_heading(organizer, "Organizer studio")
        workshop = organizer.get_by_role("article").filter(has_text="Design Lab: Figma 101")
        workshop.get_by_role("link", name="Attendees").click()
        wait_for_heading(organizer, "Attendees")
        expect(organizer.get_by_text(DEMO_USERS[0][0], exact=True)).to_be_visible()
        student.get_by_role("button", name="Cancel registration").click()
        student.get_by_role("dialog").get_by_role("button", name="Cancel registration").click()
        expect(student.get_by_text("Registration cancelled", exact=True)).to_be_visible()
        organizer.reload()
        expect(organizer.get_by_role("cell", name="Cancelled", exact=True)).to_be_visible()

        organizer.get_by_role("link", name="Back to organizer studio").click()
        organizer.get_by_role("link", name="Create event").click()
        wait_for_heading(organizer, "Create event")
        organizer.get_by_label("Event title").fill("Browser QA Club Meetup")
        organizer.get_by_role("combobox", name="Category", exact=True).select_option("Community")
        organizer.get_by_label("Organizer or club").fill("Club Council")
        organizer.get_by_label("Venue").fill("Campus Commons")
        start = datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=4)
        times = {"starts_at": start, "ends_at": start + timedelta(hours=2),
                 "closes_at": start - timedelta(days=1)}
        for field, value in times.items():
            organizer.locator(f'input[name="{field}"]').fill(value.isoformat(timespec="minutes")[:16])
        organizer.get_by_label("Capacity").fill("30")
        organizer.get_by_label("Description").fill("A browser smoke test for publishing a campus event.")
        organizer.get_by_label("Eligibility").fill("Open to all students.")
        organizer.get_by_role("button", name="Save draft").click()
        item = organizer.get_by_role("article").filter(has_text="Browser QA Club Meetup")
        expect(item.get_by_text("Draft", exact=True)).to_be_visible()
        item.get_by_role("link", name="Edit", exact=True).click()
        organizer.get_by_role("button", name="Publish event").click()
        expect(item.get_by_text("Open", exact=True)).to_be_visible()
        item.get_by_role("button", name="Cancel event").click()
        organizer.get_by_role("dialog").get_by_role("button", name="Cancel event").click()
        expect(item.get_by_text("Cancelled", exact=True)).to_be_visible()
        item.get_by_role("button", name="Archive").click()
        organizer.get_by_role("dialog").get_by_role("button", name="Archive event").click()
        expect(item.get_by_text("Archived", exact=True)).to_be_visible()

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  device_scale_factor=1)
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto(ORIGIN)
        wait_for_heading(mobile, "Good things happen here.")
        assert mobile.locator("html").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        if args.screenshots:
            mobile.screenshot(path=args.screenshots / "campusloop-mobile.png", full_page=True)
        mobile.goto(args.preview.resolve().as_uri())
        wait_for_heading(mobile, "Good things happen here.")
        mobile.get_by_role("button", name="Try student").click()
        wait_for_heading(mobile, "My events")
        mobile.get_by_role("button", name="Try organizer").click()
        wait_for_heading(mobile, "Organizer studio")
        assert mobile.locator("html").evaluate("el => el.scrollWidth <= el.clientWidth + 1")

        restricted = browser.new_page(viewport={"width": 390, "height": 844}, java_script_enabled=False)
        restricted.goto(args.preview.resolve().as_uri())
        wait_for_heading(restricted, "Good things happen here.")
        expect(restricted.get_by_text("Loading CampusLoop…", exact=True)).to_have_count(0)
        restricted.get_by_role("link", name="Explore events", exact=True).click()
        restricted.locator("summary").filter(has_text="Design Lab: Figma 101").click()
        expect(restricted.get_by_text("A practical introduction", exact=False)).to_be_visible()
        for label, heading in (("Student sign-in walkthrough", "Student walkthrough"),
                               ("Organisation sign-in walkthrough", "Organizer walkthrough")):
            restricted.get_by_role("link", name=label).click()
            expect(restricted.get_by_role("heading", name=heading)).to_be_visible()

        assert not errors, errors
        browser.close()
    print("Chromium passed: desktop, Android-sized review, student registration and reload, organizer workflow, and keyboard skip link.")


if __name__ == "__main__":
    main()
