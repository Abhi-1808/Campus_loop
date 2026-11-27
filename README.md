# CampusLoop

CampusLoop is a responsive, single-campus event portal. It centralizes event discovery, registration, and organizer workflows in a shared database. The project follows the scope from **Campus Event Portal Analysis** and **Campus Event Research**.

| Area | What works |
| --- | --- |
| Discovery | Home, category shortcuts, searchable and paginated event listings, deadlines, availability, and event details |
| Student | Sign-in, registration, cancellation, registration history, and seat counts |
| Organizer | Draft, publish, edit, cancel, and archive owned events. View attendee records for owned events. |
| Operations | Explicit account provisioning, password rotation, deactivation, database initialization and backup, health endpoint |

## Open the review edition

Open `CampusLoop-Review.html` to browse the homepage, sample events, and both role walkthroughs in any HTML viewer. In a browser with JavaScript enabled, use **Try student** or **Try organizer** to exercise the same app interface with in-memory demo data. If your phone opens the file in a document viewer, download it and open it in Chrome for the interactive controls. Reloading resets the interactive sample state.

## Run the shared-database edition

Requires Python 3.12 or newer. From this directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m campusloop seed-demo
python -m campusloop serve
```

On Windows PowerShell, create the environment with `py -m venv .venv` and activate it with `.\.venv\Scripts\Activate.ps1`. Use the exact browser address [http://127.0.0.1:8000](http://127.0.0.1:8000) for the default configuration.

| Local account | Email |
| --- | --- |
| Student | `student@campusloop.example` |
| Organizer | `organizer@campusloop.example` |

Both local review accounts use `CampusLoop-Demo-2026`. The seeding command is opt-in. It adds 12 fictional sample events and preserves previously changed sample records. Use a new development database path for a fresh demo.

Select **Sign in**, then **Student sign-in** or **Organisation sign-in**. The organisation page is for approved organiser accounts serving clubs, societies, or departments.

## How it works

- The browser loads HTML, CSS, and JavaScript from the same origin as the FastAPI service.
- SQLite stores users, sessions, login limits, events, and registrations. The default rollback journal and an immediate transaction serialize seat-taking and capacity changes. Unique constraints prevent duplicate event registrations. Version checks protect concurrent organizer edits.
- Published events are discoverable. Drafts stay with their owner. Organizers can cancel upcoming events and archive drafts, cancelled events, and completed events. Archiving keeps registrations available to the organizer and to students with a registration record.
- Students use managed accounts. Organizers publish through the same interface with server-enforced ownership checks. Event schedules and deadlines display in Asia/Kolkata.
- The application uses scrypt for password hashes and stores session-token digests. It uses same-origin JSON writes, secure HTTPS cookies in production, expiring sessions, and account/IP login throttling. The frontend uses semantic links, labelled controls, keyboard focus, and reduced-motion support.

## Verify

```sh
python -m pip install httpx==0.28.1
python -m unittest discover -s tests -v
```

To run the optional Chromium smoke test with Playwright:

```sh
python -m pip install playwright
python -m playwright install chromium
python -m review.build CampusLoop-Review.html
PYTHONPATH=. python tests/browser_review.py --preview CampusLoop-Review.html
```

The test can also take `--chromium /path/to/chromium`. It starts an isolated database, checks both browser roles, and stops its local server. For operational setup, see [Deployment and handoff](DEPLOYMENT.md).

## Research decisions

- The first CampusLoop prototype established the seven views, event categories, and student and organizer journeys. This build keeps that scope and puts shared records and access checks on the server.
- Luma’s event-first registration workflow informed the placement of the registration action on the event detail page. [Luma registration flow](https://help.luma.com/p/event-registration-process)
- Labelling, keyboard focus, reflow, and status text were reviewed against the W3C guidance. [WCAG 2.2 reference](https://www.w3.org/WAI/WCAG22/quickref/)
- The original research included a US student survey and a proposed local questionnaire. No Bennett University survey responses were collected for this build.
- The campus photo is generated illustrative artwork. The organizations, accounts, and sample listings in the review are fictional.
