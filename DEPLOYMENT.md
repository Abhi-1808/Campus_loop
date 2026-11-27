# Deployment and handoff

CampusLoop targets a single university campus and a single application host with a persistent local SQLite volume. The checked-in code can run as a supervised non-root service behind an HTTPS reverse proxy.

## Configure the host

1. Give the service account ownership of its persistent database directory. Run the application from a Python virtual environment with the pinned dependencies.
2. Set `CAMPUSLOOP_ENV=production`, `CAMPUSLOOP_ORIGIN` to the approved HTTPS origin with no trailing slash, and `CAMPUSLOOP_DB` to an absolute database file on local storage. Use a fresh production database. Startup rejects the two local demo accounts.
3. Keep the app bound to loopback. Terminate HTTPS at the reverse proxy, preserve the public Host header, redirect plain HTTP to HTTPS, and enforce an appropriate ingress request limit for the 16 KiB JSON API.
4. If the proxy is the only route to the service, set `CAMPUSLOOP_TRUSTED_PROXY` to its exact IP and configure it to overwrite inbound forwarding headers. For same-host deployments the value is typically `127.0.0.1`. This lets the application apply IP throttling to client addresses.
5. Provision institutional accounts through the trusted service operator. Event ownership follows the organizer account, so give societies an institutional account lifecycle before seeding events.

```sh
export CAMPUSLOOP_ENV=production
export CAMPUSLOOP_ORIGIN=https://events.example.edu
export CAMPUSLOOP_DB=/var/lib/campusloop/campusloop.sqlite3
export CAMPUSLOOP_TRUSTED_PROXY=127.0.0.1

python -m campusloop init
python -m campusloop user student@example.edu "Student Name" student
python -m campusloop user organizer@example.edu "Society Name" organizer
python -m campusloop serve --host 127.0.0.1 --port 8000
```

The `user` command prompts for the password. Use `--update` for an existing account and `deactivate EMAIL` to revoke its sessions and access. The release uses application-managed accounts. University SSO, if institutionally required, needs the university’s identity-provider registration and a separate integration. Alerts and event status changes appear in the application. This release has no outbound email delivery.

## Verify before admitting students

- Check `GET /healthz` from host monitoring, then sign in through the approved HTTPS origin from a campus device. Verify both roles and confirm the live app sets an HTTPS session cookie.
- Assign a service owner and agree on the contact, student data retention, handling of access requests, and backup policy with the university. The service stores name, campus email, department, year, and registration history. Organizer access covers their own events.
- Exercise a capacity-limited test event at expected campus load and monitor availability, latency, and throttling. The local tests cover correctness at the last seat. Production capacity and institutional network behavior depend on the target host.
- Back up the database to a protected location. Verify restoration to a separate file before opening attendance to students.

```sh
python -m campusloop backup /var/backups/campusloop/campusloop-2026-11-27.sqlite3
```

The backup command uses SQLite’s online backup API, removes session and sign-in throttling records from the copy, and checks its integrity. Restore during a maintenance window with the service stopped, preserve the prior database, and verify the copy using the same application release before opening traffic. Users sign in again after a restore. Treat database backups as student data and keep them out of version control.

## Technical references

- [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/)
- [SQLite transaction behavior](https://www.sqlite.org/lang_transaction.html)
- [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
