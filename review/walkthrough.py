"""Static review content for viewers that disable JavaScript."""

from datetime import datetime
from html import escape


EVENT_MARKS = {
    "Technical": "⌘",
    "Cultural": "✳",
    "Workshop": "✎",
    "Sports": "◈",
    "Academic": "◇",
    "Community": "◎",
}


def heading_date(value, zone):
    local = datetime.fromisoformat(value).astimezone(zone)
    return f"{local:%a}, {local.day} {local:%b}"


def featured_card(event, zone):
    category = event["category"]
    identifier = escape(event["id"])
    date = heading_date(event["starts_at"], zone)
    return f"""<a class="card" href="#sample-{identifier}">
      <div class="art art-{escape(category.lower())}" aria-hidden="true">
        <span class="art-label">{escape(category)}</span>
        <span class="art-mark">{EVENT_MARKS[category]}</span>
      </div>
      <div class="card-body">
        <p class="card-meta">{date} · {escape(category)}</p>
        <h3>{escape(event["title"])}</h3>
        <p class="card-meta">{escape(event["organizer"])} · {escape(event["venue"])}</p>
        <div class="card-foot"><span class="pill open">{event["seats_left"]} seats left</span><span>View event</span></div>
      </div>
    </a>"""


def sample_listing(event, zone):
    identifier = escape(event["id"])
    date = heading_date(event["starts_at"], zone)
    deadline = heading_date(event["closes_at"], zone)
    return f"""<article class="item" id="sample-{identifier}">
      <details>
        <summary><strong>{escape(event["title"])}</strong> · {escape(event["category"])} · {date}</summary>
        <p class="subtle">{escape(event["organizer"])} · {escape(event["venue"])} · {event["seats_left"]} seats left</p>
        <p>{escape(event["description"])}</p>
        <p><strong>Registration deadline</strong> {deadline}</p>
        <p><strong>Eligibility</strong> {escape(event["eligibility"])}</p>
      </details>
    </article>"""


def render_walkthrough(events, zone, photo):
    banner = """<div id="preview-banner" class="preview-strip">
      <div class="wrap">Review edition · Fictional events
        <span class="preview-buttons">
          <a class="text-link" href="#preview-student">Student sign-in walkthrough</a>
          <a class="text-link" href="#preview-organizer">Organisation sign-in walkthrough</a>
        </span>
      </div>
    </div>"""
    cards = "".join(featured_card(event, zone) for event in events[:3])
    listings = "".join(sample_listing(event, zone) for event in events)
    walkthrough = f"""
    <section class="hero" id="home">
      <div class="hero-copy">
        <p class="label">Your campus calendar</p><h1>Good things<br>happen <em>here.</em></h1>
        <p>Find campus events worth showing up for. From club workshops to late-night performances, everything is in one place.</p>
        <a class="button lime" href="#events">Explore events</a>
      </div>
      <figure class="hero-media">
        <img id="review-hero" src="data:image/webp;base64,{photo}" width="1536" height="1024"
             alt="Students gathering at an outdoor campus club fair" fetchpriority="high">
      </figure>
    </section>
    <section class="section" aria-labelledby="upcoming-title">
      <div class="section-head">
        <h2 id="upcoming-title">Coming up on campus</h2><a class="text-link" href="#events">All events</a>
      </div>
      <div class="grid">{cards}</div>
    </section>
    <section class="section" aria-labelledby="events-title" id="events">
      <div class="section-head"><h2 id="events-title">Explore events</h2></div>
      <div class="list">{listings}</div>
    </section>
    <section class="section panel" id="preview-student" aria-labelledby="student-title">
      <h2 id="student-title">Student walkthrough</h2>
      <ol>
        <li>Choose an event and check its venue, date, eligibility, and available seats.</li>
        <li>Choose Student sign-in, enter your department and year when registering, and confirm.</li>
        <li>Open My events to view or cancel your registration.</li>
      </ol>
      <article class="item"><div>
        <h3>Design Lab: Figma 101</h3>
        <p class="subtle">Computer Lab 2 · Sample registration</p>
      </div><span class="pill open">Registered</span></article>
    </section>
    <section class="section panel" id="preview-organizer" aria-labelledby="organizer-title">
      <h2 id="organizer-title">Organizer walkthrough</h2>
      <ol>
        <li>Choose Organisation sign-in and use an approved organiser account.</li>
        <li>Create a draft with a title, category, venue, schedule, and capacity.</li>
        <li>Publish to the campus calendar and open Attendees to see registrations.</li>
        <li>Edit upcoming details, cancel an event, or archive it to preserve its history.</li>
      </ol>
      <article class="item"><div>
        <h3>Design Lab: Figma 101</h3>
        <p class="subtle">Sample organizer view · 1 registration</p>
      </div><span class="pill open">Published</span></article>
    </section>
    <section class="section panel" id="about" aria-labelledby="about-title">
      <h2 id="about-title">About CampusLoop</h2>
      <p>CampusLoop brings university events, schedules, and registrations into one shared calendar.</p>
      <p class="subtle">To try the interactive forms, download this HTML file and open it in a browser with JavaScript enabled.</p>
    </section>
    """
    return banner, walkthrough
