from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CATEGORIES = ("Technical", "Cultural", "Workshop", "Sports", "Academic", "Community")
YEAR_LABELS = {"1": "Year 1", "2": "Year 2", "3": "Year 3", "4": "Year 4", "PG": "Postgraduate", "Other": "Other"}


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Payload):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    role: Literal["student", "organizer"] | None = None

    # Passwords must retain leading and trailing characters.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class EventForm(Payload):
    title: str = Field(min_length=3, max_length=100)
    category: Literal["Technical", "Cultural", "Workshop", "Sports", "Academic", "Community"]
    organizer: str = Field(min_length=2, max_length=90)
    venue: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=3500)
    eligibility: str = Field(min_length=2, max_length=350)
    starts_at: str = Field(min_length=16, max_length=16)
    ends_at: str = Field(min_length=16, max_length=16)
    closes_at: str = Field(min_length=16, max_length=16)
    capacity: int = Field(ge=1, le=5000, strict=True)
    status: Literal["draft", "published"]
    version: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("starts_at", "ends_at", "closes_at")
    @classmethod
    def validate_local_time(cls, value):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("Enter a valid date and time.") from None
        if value != parsed.isoformat(timespec="minutes") or parsed.year < 2000:
            raise ValueError("Enter a valid date and time.")
        return value

    @model_validator(mode="after")
    def validate_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("The event must end after it starts.")
        if self.closes_at > self.starts_at:
            raise ValueError("Registration must close by the event start.")
        return self

    def database_values(self, timezone):
        def timestamp(value):
            return int(datetime.fromisoformat(value).replace(tzinfo=timezone).timestamp())

        return (
            self.title, self.category, self.organizer, self.venue, self.description,
            self.eligibility, timestamp(self.starts_at), timestamp(self.ends_at),
            timestamp(self.closes_at), self.capacity, self.status,
        )


class RegistrationForm(Payload):
    department: str = Field(min_length=2, max_length=90)
    year: Literal["1", "2", "3", "4", "PG", "Other"]


class RegistrationCancellation(Payload):
    registration_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class Revision(Payload):
    version: int = Field(ge=1, strict=True)
