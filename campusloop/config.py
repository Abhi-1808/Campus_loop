import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_TIME_ZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class Settings:
    database: Path
    origin: str
    production: bool
    timezone: str = DEFAULT_TIME_ZONE

    @classmethod
    def from_env(cls):
        environment = os.environ.get("CAMPUSLOOP_ENV", "development")
        if environment not in {"development", "production"}:
            raise ValueError("CAMPUSLOOP_ENV must be development or production.")
        production = environment == "production"
        origin = os.environ.get("CAMPUSLOOP_ORIGIN", "" if production else "http://127.0.0.1:8000")
        parsed = urlsplit(origin)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname
        if not valid or parsed.username or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("Set CAMPUSLOOP_ORIGIN to an origin with no trailing slash or path.")
        if production and parsed.scheme != "https":
            raise ValueError("Production requires an HTTPS CAMPUSLOOP_ORIGIN.")
        database = os.environ.get("CAMPUSLOOP_DB")
        if production and (not database or not Path(database).is_absolute()):
            raise ValueError("Production requires an absolute CAMPUSLOOP_DB path on persistent storage.")
        return cls(Path(database or "instance/campusloop.sqlite3").resolve(), origin, production)

    @property
    def host(self):
        return urlsplit(self.origin).hostname

    @property
    def zone(self):
        return ZoneInfo(self.timezone)

    @property
    def cookie_name(self):
        return "__Host-campusloop" if self.production else "campusloop"
