"use strict";
const categories = {Technical: "⌘", Cultural: "✳", Workshop: "✎", Sports: "◈", Academic: "◇", Community: "◎"};
const years = {"1": "Year 1", "2": "Year 2", "3": "Year 3", "4": "Year 4", PG: "Postgraduate", Other: "Other"};
const statuses = {upcoming: "Upcoming", open: "Registration open", past: "Past and cancelled", all: "All events"};
const orders = {soon: "Earliest first", latest: "Latest first", deadline: "Deadline first"};
const signInOptions = {
  student: {title: "Student sign-in", description: "Use your student account to register and manage your events."},
  organizer: {title: "Organisation sign-in", description: "Use your approved club, society, or department organiser account."},
};
const main = document.querySelector("#main");
const nav = document.querySelector("#nav");
const account = document.querySelector("#account");
const feedback = document.querySelector("#feedback");
const dialog = document.querySelector("#confirm");
const preview = window.campusloopPreview;
let state = {user: null, timezone: "Asia/Kolkata"};
let renderId = 0;
let initialized = false;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}
const eventLink = id => "#events/" + encodeURIComponent(id);
const manageLink = id => "#studio/" + encodeURIComponent(id);

function queryString(values) {
  const items = Object.entries(values).filter(([, value]) => value !== "" && value != null);
  return items.length ? "?" + new URLSearchParams(items) : "";
}

function message(text, error = false) {
  feedback.innerHTML = text ? `<p class="feedback-note${error ? " error" : ""}">${esc(text)}</p>` : "";
}

async function api(path, method = "GET", body = {}) {
  if (preview) return preview.request(path, method, body);
  const options = {method, credentials: "same-origin", cache: "no-store"};
  if (method !== "GET") {
    options.headers = {"Content-Type": "application/json", "X-CampusLoop-Request": "1"};
    options.body = JSON.stringify(body);
  }
  const response = await fetch("/api" + path, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.detail || "CampusLoop could not complete the request. Try again.");
    error.status = response.status;
    error.fields = result.fields;
    throw error;
  }
  return result;
}

function route() {
  const hash = location.hash.slice(1) || "home";
  const offset = hash.indexOf("?");
  return {
    path: (offset < 0 ? hash : hash.slice(0, offset)).split("/"),
    query: new URLSearchParams(offset < 0 ? "" : hash.slice(offset + 1)),
  };
}

function exploreLink(values = {}) {
  return "#events" + queryString({
    q: values.q || "", category: values.category || "",
    status: values.status === "upcoming" ? "" : values.status,
    order: values.order === "soon" ? "" : values.order,
    page: Number(values.page) > 1 ? values.page : "",
  });
}

function dateText(value, options = {weekday: "short", day: "numeric", month: "short"}) {
  const text = new Intl.DateTimeFormat("en-IN", {...options, timeZone: state.timezone}).format(new Date(value));
  return `<time datetime="${esc(value)}">${esc(text)}</time>`;
}

function fullDate(value) {
  return dateText(value, {day: "numeric", month: "short", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short"});
}

function localInput(value) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: state.timezone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = Object.fromEntries(parts.map(item => [item.type, item.value]));
  return `${part.year}-${part.month}-${part.day}T${part.hour}:${part.minute}`;
}

function button(label, href, style = "") {
  return `<a class="button ${style}" href="${esc(href)}">${esc(label)}</a>`;
}

function action(label, name, {style = "outline small", id = "", version = "", registrationId = ""} = {}) {
  return `<button class="button ${style}" type="button" data-action="${name}" data-id="${esc(id)}"
    data-version="${esc(version)}" data-registration-id="${esc(registrationId)}">${esc(label)}</button>`;
}

const formError = '<div class="form-error" role="alert" tabindex="-1" hidden></div>';

function displayFormError(form, error) {
  const area = form.querySelector(".form-error");
  const entries = Object.entries(error.fields || {}).map(([field, value]) =>
    `<li>${esc(field)} · ${esc(value)}</li>`).join("");
  area.innerHTML = "<strong>" + esc(error.message) + "</strong>" + (entries ? "<ul>" + entries + "</ul>" : "");
  area.hidden = false;
  area.focus();
}

function options(values, selected) {
  const entries = Object.entries(values).filter(([value]) => value !== "");
  if (Object.hasOwn(values, "")) entries.unshift(["", values[""]]);
  return entries.map(([value, label]) =>
    `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
}

const categoryOptions = Object.fromEntries(Object.keys(categories).map(key => [key, key]));

function pageTitle(title, description, right = "") {
  return `<header class="page-intro${right ? " split" : ""}"><div><h1>${esc(title)}</h1><p class="subtle">${esc(description)}</p></div>${right}</header>`;
}

function empty(title, text, next = "") {
  return `<div class="empty"><h2>${esc(title)}</h2><p>${esc(text)}</p>${next}</div>`;
}

function badge(label, style = "") {
  return `<span class="pill ${esc(style)}">${esc(label)}</span>`;
}

function art(event, large = false) {
  return `<div class="art art-${esc(event.category.toLowerCase())}${large ? " art-large" : ""}" aria-hidden="true">
    <span class="art-label">${esc(event.category)}</span>
    <span class="art-mark">${categories[event.category] || "◎"}</span>
  </div>`;
}

function card(event) {
  const seats = event.state === "open" ? `${event.seats_left} seats left` : event.state_label;
  return `<a class="card" href="${eventLink(event.id)}">
    ${art(event)}<div class="card-body">
      <p class="card-meta">${dateText(event.starts_at)} · ${esc(event.category)}</p>
      <h3>${esc(event.title)}</h3>
      <p class="card-meta">${esc(event.organizer)} · ${esc(event.venue)}</p>
      <div class="card-foot">${badge(seats, event.state)}<span>View event</span></div>
    </div>
  </a>`;
}

function stat(value, label) {
  return `<div class="stat"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;
}

function updateHeader() {
  const links = {Home: "#home", Explore: "#events", About: "#about"};
  if (state.user?.role === "student") links["My events"] = "#my-events";
  if (state.user?.role === "organizer") links["Organizer studio"] = "#studio";
  const active = route().path[0];
  nav.innerHTML = Object.entries(links).map(([label, href]) =>
    `<a href="${href}"${href === "#" + active ? ' aria-current="page"' : ""}>${label}</a>`).join("");
  account.innerHTML = state.user
    ? `<span class="account-name">${esc(state.user.name)}</span>${action("Sign out", "logout")}`
    : button("Sign in", "#login", "small");
}

async function home() {
  const {events} = await api("/events");
  const hero = preview?.hero || "/assets/images/campus-life.webp";
  const chips = Object.entries(categories).map(([label, icon]) =>
    `<a class="chip" href="${exploreLink({category: label})}"><span class="chip-mark" aria-hidden="true">${icon}</span>${label}</a>`).join("");
  const cards = events.length ? events.slice(0, 3).map(card).join("") :
    empty("No upcoming events", "Check back once campus organizers publish their next events.");
  return ["Campus events", `<section class="hero">
    <div class="hero-copy">
      <p class="label">Your campus calendar</p><h1>Good things<br>happen <em>here.</em></h1>
      <p>Find campus events worth showing up for. From club workshops to late-night performances, everything is in one place.</p>
      ${button("Explore events", "#events", "lime")}
    </div>
    <figure class="hero-media"><img src="${esc(hero)}" width="1536" height="1024" alt="Students gathering at an outdoor campus club fair" fetchpriority="high"></figure>
  </section>
  <section class="section" aria-labelledby="categories-title">
    <div class="section-head"><h2 id="categories-title">Browse by category</h2></div>
    <div class="chips">${chips}</div>
  </section>
  <section class="section" aria-labelledby="upcoming-title">
    <div class="section-head"><h2 id="upcoming-title">Coming up on campus</h2><a class="text-link" href="#events">All events</a></div>
    <div class="grid">${cards}</div>
  </section>`];
}

async function explore(query) {
  const category = Object.hasOwn(categories, query.get("category")) ? query.get("category") : "";
  const filters = {
    q: (query.get("q") || "").slice(0, 120), category,
    status: Object.hasOwn(statuses, query.get("status")) ? query.get("status") : "upcoming",
    order: Object.hasOwn(orders, query.get("order")) ? query.get("order") : "soon",
    page: Math.min(10000, Math.max(1, Number.parseInt(query.get("page"), 10) || 1)),
  };
  const result = await api("/events" + queryString(filters));
  const pagination = result.pages > 1 ? `<nav class="pagination" aria-label="Event result pages">
    ${result.page > 1 ? button("Previous", exploreLink({...filters, page: result.page - 1}), "outline small") : ""}
    <span>Page ${result.page} of ${result.pages}</span>
    ${result.page < result.pages ? button("Next", exploreLink({...filters, page: result.page + 1}), "outline small") : ""}
  </nav>` : "";
  const cards = result.events.length ? result.events.map(card).join("") :
    empty("No events found", "Try different search terms or clear the filters.", button("Clear filters", "#events", "outline"));
  return ["Explore events", `${pageTitle("Explore events", "Find workshops, competitions, performances, and more across campus.")}
    <form class="filters" id="event-filters" role="search">
      <label class="field query">Search events<input name="q" type="search" maxlength="120" value="${esc(filters.q)}" placeholder="Try a title, club, or venue"></label>
      <label class="field facet">Category<select name="category">${options({"": "All categories", ...categoryOptions}, category)}</select></label>
      <label class="field facet">Availability<select name="status">${options(statuses, filters.status)}</select></label>
      <label class="field facet">Sort by<select name="order">${options(orders, filters.order)}</select></label>
      <button class="button">Apply filters</button>
    </form>
    <p class="result-count">${result.total} event${result.total === 1 ? "" : "s"}</p>
    <div class="grid">${cards}</div>${pagination}`];
}

function signInLink(role, next) {
  return (role ? "#login/" + role : "#login") + queryString({next});
}

function accessPage(role, next) {
  const title = role === "student" ? "Student access" : "Organizer access";
  const text = state.user ? `This page requires a ${role} account.` : `Sign in with a ${role} account to continue.`;
  return [title, empty(title, text, state.user
    ? action("Sign out", "logout") : button("Sign in", signInLink(role, next)))];
}

async function detail(id) {
  const {event, registration} = await api("/events/" + encodeURIComponent(id));
  const isRegistered = registration && !registration.cancelled_at;
  let next = "";
  if (isRegistered) {
    const label = event.status === "cancelled" ? "This event was cancelled." : "You’re registered for this event.";
    next = `<p class="notice">${label}</p>${button("View my events", "#my-events", "block")}`;
  } else if (event.state === "open" && state.user?.role !== "organizer") {
    const target = eventLink(id) + "/register";
    next = state.user ? button("Register for event", target, "block") :
      button("Sign in to register", signInLink("student", target), "block");
  }
  return [event.title, `<a href="#events" class="text-link back">Back to events</a><div class="detail-layout">
    <article class="panel detail-main">${art(event, true)}<div class="reading">
      ${badge(event.state_label, event.state)}
      <h1>${esc(event.title)}</h1><p class="subtle">Hosted by ${esc(event.organizer)}</p>
      <h2>About this event</h2><p class="prose">${esc(event.description)}</p>
      <h2>Who can join</h2><p class="prose">${esc(event.eligibility)}</p>
    </div></article>
    <aside class="panel" aria-labelledby="details-heading">
      <h2 id="details-heading">Event details</h2>
      <dl class="facts">
        <div><dt>Starts</dt><dd>${fullDate(event.starts_at)}</dd></div>
        <div><dt>Ends</dt><dd>${fullDate(event.ends_at)}</dd></div>
        <div><dt>Venue</dt><dd>${esc(event.venue)}</dd></div>
        <div><dt>Registration closes</dt><dd>${fullDate(event.closes_at)}</dd></div>
        <div><dt>Seats available</dt><dd>${event.seats_left} of ${event.capacity}</dd></div>
      </dl>${next}
    </aside>
  </div>`];
}

async function registrationPage(id) {
  if (state.user?.role !== "student") return accessPage("student", eventLink(id) + "/register");
  const {event, registration} = await api("/events/" + encodeURIComponent(id));
  if (event.state !== "open" || (registration && !registration.cancelled_at)) {
    return ["Registration unavailable", empty("Registration unavailable",
      "This event is closed, full, or you already have a registration.", button("View event", eventLink(id)))];
  }
  return ["Register for event", `<a class="back text-link" href="${eventLink(id)}">Back to event</a>
    ${pageTitle("Register for event", event.title)}
    <section class="panel form-page">
      <h2>Student details</h2>
      <p class="subtle">${esc(state.user.name)} · ${esc(state.user.email)}</p>
      <form id="register-form" data-event="${esc(id)}" class="section-label">
        ${formError}<div class="form-grid">
          <label class="field">Department<input name="department" required minlength="2" maxlength="90" placeholder="Computer Science"></label>
          <label class="field">Year<select name="year" required>${options({"": "Select your year", ...years}, "")}</select></label>
        </div>
        <div class="actions form-actions">${button("Go back", eventLink(id), "outline")}<button class="button">Confirm registration</button></div>
      </form>
    </section>`];
}

function registrationRow({event, registration}) {
  const dropped = Boolean(registration.cancelled_at);
  const future = new Date(event.starts_at).getTime() > Date.now();
  const labels = {cancelled: "Event cancelled", archived: "Archived"};
  const label = dropped ? "Registration cancelled" : (labels[event.status] || (future ? "Registered" : event.state_label));
  const active = !dropped && future && event.status === "published";
  const cancel = active ? action("Cancel registration", "cancel-registration", {
    id: event.id, registrationId: registration.id,
  }) : "";
  return `<article class="item"><div>
    <h3><a href="${eventLink(event.id)}">${esc(event.title)}</a></h3>
    <p class="subtle">${dateText(event.starts_at)} · ${esc(event.venue)}</p>
    <p class="subtle">Registration ${esc(registration.id.slice(0, 8).toUpperCase())}</p>
  </div><div class="actions">${badge(label, active ? "open" : "")}${cancel}</div></article>`;
}

async function myEvents() {
  if (state.user?.role !== "student") return accessPage("student", "#my-events");
  const {items} = await api("/my-events");
  const active = items.filter(({event, registration}) => !registration.cancelled_at &&
    event.status === "published" && new Date(event.ends_at).getTime() > Date.now());
  const previous = items.filter(item => !active.includes(item));
  const currentList = active.length ? active.map(registrationRow).join("") : empty(
    "Nothing on your calendar", "Your confirmed registrations will appear here.", button("Explore events", "#events", "outline"));
  return ["My events", `${pageTitle("My events", "Manage your campus registrations and see what’s next.", button("Find events", "#events", "outline"))}
    <div class="stats">${stat(active.length, "Current")}${stat(previous.length, "Past or cancelled")}${stat(items.length, "All registrations")}</div>
    <h2 class="section-label">Current registrations</h2><div class="list">${currentList}</div>
    ${previous.length ? `<h2 class="section-label">Past and cancelled</h2><div class="list">${previous.map(registrationRow).join("")}</div>` : ""}`];
}

function organizerRow(event) {
  const editable = ["draft", "open", "full", "closed"].includes(event.state);
  const canCancel = event.status === "published" && new Date(event.starts_at).getTime() > Date.now();
  const canArchive = event.status !== "archived" &&
    (event.status !== "published" || event.state === "completed");
  const controls = {id: event.id, version: event.version};
  const href = manageLink(event.id);
  return `<article class="item"><div>
    <h3><a href="${href}/attendees">${esc(event.title)}</a></h3>
    <p class="subtle">${dateText(event.starts_at)} · ${esc(event.venue)} · ${event.registrations} registered</p>
  </div><div class="actions">${badge(event.state_label, event.state)}
    ${button("Attendees", href + "/attendees", "outline small")}
    ${editable ? button("Edit", href, "outline small") : ""}
    ${canCancel ? action("Cancel event", "cancel-event", controls) : ""}
    ${canArchive ? action("Archive", "archive-event", controls) : ""}
  </div></article>`;
}

async function studio() {
  if (state.user?.role !== "organizer") return accessPage("organizer", "#studio");
  const {events} = await api("/organizer/events");
  const current = events.filter(event => event.status !== "archived");
  const archived = events.filter(event => event.status === "archived");
  const currentList = current.length ? current.map(organizerRow).join("") : empty(
    "No events yet", "Create a draft to start organizing your first event.", button("Create event", "#studio/new"));
  return ["Organizer studio", `${pageTitle("Organizer studio", "Publish events, track attendance, and keep details current.", button("Create event", "#studio/new"))}
    <div class="stats">${stat(current.filter(event => event.status === "published").length, "Published")}
      ${stat(current.filter(event => event.status === "draft").length, "Drafts")}
      ${stat(current.reduce((sum, event) => sum + event.registrations, 0), "Active registrations")}</div>
    <h2 class="section-label">Your events</h2><div class="list">${currentList}</div>
    ${archived.length ? `<h2 class="section-label">Archived</h2><div class="list">${archived.map(organizerRow).join("")}</div>` : ""}`];
}

function textField(label, name, value, attributes = "") {
  return `<label class="field">${label}<input name="${name}" value="${esc(value)}" ${attributes}></label>`;
}

async function eventForm(id) {
  if (state.user?.role !== "organizer") return accessPage("organizer", id ? manageLink(id) : "#studio/new");
  const event = id ? (await api("/organizer/events/" + encodeURIComponent(id))).event : {};
  if (id && ["cancelled", "archived", "ongoing", "completed"].includes(event.state)) {
    return ["Event is read-only", empty("Event is read-only", "See the organizer studio for available actions.",
      button("Organizer studio", "#studio"))];
  }
  const title = id ? "Edit event" : "Create event";
  return [title, `<a class="back text-link" href="#studio">Back to organizer studio</a>
    ${pageTitle(title, "Enter campus-local dates and choose whether to save a draft or publish.")}
    <form class="panel form-page" id="event-form" data-id="${esc(id || "")}" data-version="${event.version || ""}">
      ${formError}<div class="form-grid">
        ${textField("Event title", "title", event.title, 'required minlength="3" maxlength="100"')}
        <label class="field">Category<select name="category" required>${options({"": "Select a category", ...categoryOptions}, event.category || "")}</select></label>
        ${textField("Organizer or club", "organizer", event.organizer, 'required minlength="2" maxlength="90"')}
        ${textField("Venue", "venue", event.venue, 'required minlength="2" maxlength="120"')}
        ${textField("Starts", "starts_at", localInput(event.starts_at), 'type="datetime-local" required')}
        ${textField("Ends", "ends_at", localInput(event.ends_at), 'type="datetime-local" required')}
        ${textField("Registration deadline", "closes_at", localInput(event.closes_at), 'type="datetime-local" required')}
        ${textField("Capacity", "capacity", event.capacity, 'type="number" min="1" max="5000" required')}
        <label class="field full">Description<textarea name="description" required minlength="10" maxlength="3500">${esc(event.description)}</textarea></label>
        <label class="field full">Eligibility<textarea name="eligibility" required minlength="2" maxlength="350">${esc(event.eligibility)}</textarea></label>
      </div><div class="actions form-actions">
        ${button("Go back", "#studio", "outline")}
        ${event.status !== "published" ? '<button class="button outline" name="status" value="draft">Save draft</button>' : ""}
        <button class="button" name="status" value="published">${event.status === "published" ? "Save changes" : "Publish event"}</button>
      </div>
    </form>`];
}

async function attendees(id) {
  if (state.user?.role !== "organizer") return accessPage("organizer", manageLink(id) + "/attendees");
  const {event, items} = await api("/organizer/events/" + encodeURIComponent(id) + "/attendees");
  const rows = items.map(item => `<tr><th scope="row">${esc(item.name)}</th><td>${esc(item.email)}</td>
    <td>${esc(item.department)}</td><td>${esc(years[item.year])}</td>
    <td>${item.cancelled_at ? badge("Cancelled", "cancelled") : badge("Registered", "open")}</td></tr>`).join("");
  const table = items.length ? `<section class="panel table-wrap" tabindex="0" aria-label="Scrollable attendee table">
    <table aria-label="Event attendees"><thead><tr><th scope="col">Name</th><th scope="col">Email</th>
    <th scope="col">Department</th><th scope="col">Year</th><th scope="col">Status</th></tr></thead><tbody>${rows}</tbody></table></section>` :
    empty("No registrations yet", "Students who register for this event will appear here.");
  return ["Attendees", `<a class="back text-link" href="#studio">Back to organizer studio</a>
    ${pageTitle("Attendees", event.title)}
    <div class="stats">${stat(event.registrations, "Registered")}${stat(items.length - event.registrations, "Cancelled")}${stat(event.capacity, "Capacity")}</div>${table}`];
}

function login(role, query) {
  if (state.user) {
    return ["Signed in", empty("You’re signed in", state.user.name,
      button("Go to dashboard", state.user.role === "organizer" ? "#studio" : "#my-events"))];
  }
  const next = query.get("next") || "";
  if (!role) {
    const options = Object.entries(signInOptions).map(([key, option]) => `<a class="panel login-choice"
      aria-labelledby="login-option-${key}" href="${esc(signInLink(key, next))}">
      <h2 id="login-option-${key}">${option.title}</h2><p>${option.description}</p>
    </a>`).join("");
    return ["Sign in", `${pageTitle("Sign in", "Choose the account you use on campus.")}
      <div class="login-choices">${options}</div>`];
  }
  const {title, description} = signInOptions[role];
  const other = role === "student" ? "organizer" : "student";
  return [title, `<section class="form-narrow">
    <a href="${esc(signInLink(null, next))}" class="text-link back">All sign-in options</a>
    ${pageTitle(title, description)}
    <form class="panel" id="login-form" data-role="${role}" data-next="${esc(next)}">
      ${formError}<div class="panel-stack">
        <label class="field">Email address<input type="email" name="email" autocomplete="username" maxlength="254" required></label>
        <label class="field">Password<input type="password" name="password" autocomplete="current-password" maxlength="128" required></label>
        <button class="button">Sign in</button>
      </div>
    </form>
    <p class="section-label"><a class="text-link" href="${esc(signInLink(other, next))}">${signInOptions[other].title}</a></p>
  </section>`];
}

function about() {
  return ["About CampusLoop", `${pageTitle("About CampusLoop", "A single place to discover and manage university events.")}
    <div class="detail-layout"><section class="panel">
      <h2>Find what’s happening</h2>
      <p>CampusLoop brings campus listings, dates, eligibility, and registration into one shared calendar. Students can explore events by interest and manage reservations in My events.</p>
      <p>Club and society organizers can publish events and manage attendance in Organizer studio.</p>
    </section><section class="panel">
      <h2>Account support</h2>
      <p>Access is provisioned by the team operating CampusLoop. Contact that team if you need an account or a password reset.</p>
    </section></div>`];
}

async function page({path, query}) {
  const [section, id, subview] = path;
  if (section === "home" && !id) return home();
  if (section === "events" && !id) return explore(query);
  if (section === "events" && id && subview === "register") return registrationPage(id);
  if (section === "events" && id && !subview) return detail(id);
  if (section === "my-events" && !id) return myEvents();
  if (section === "studio" && !id) return studio();
  if (section === "studio" && id === "new" && !subview) return eventForm();
  if (section === "studio" && id && subview === "attendees") return attendees(id);
  if (section === "studio" && id && !subview) return eventForm(id);
  if (section === "login" && !subview && (!id || Object.hasOwn(signInOptions, id))) return login(id, query);
  if (section === "about" && !id) return about();
  return ["Page not found", empty("Page not found", "This CampusLoop page could not be found.", button("Go home", "#home"))];
}

async function render({focus = false} = {}) {
  const request = ++renderId;
  updateHeader();
  let result;
  try {
    result = await page(route());
  } catch (error) {
    if (request !== renderId) return;
    if (error.status === 401) {
      state.user = null;
      updateHeader();
      result = ["Sign in again", empty("Your session expired", "Sign in to continue.",
        button("Sign in", signInLink(null, location.hash)))];
    } else {
      result = ["CampusLoop", empty(error.status === 404 ? "Event not found" : "This page couldn’t load",
        error.message || "Try again in a moment.", button("Return home", "#home"))];
    }
  }
  if (request !== renderId) return;
  const [title, html] = result;
  document.title = title + " · CampusLoop";
  main.innerHTML = html;
  if (focus) {
    const heading = main.querySelector("h1, h2");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({preventScroll: true});
    }
    window.scrollTo(0, 0);
  }
}

function go(target) {
  if (location.hash === target) return render({focus: true});
  location.hash = target;
}

function safeNext(value, role) {
  if (/^#events\/[a-f0-9]{32}$/.test(value) || value === "#events") return value;
  if (role === "student" && /^#events\/[a-f0-9]{32}\/register$/.test(value)) return value;
  if (role === "organizer" && /^#studio(?:\/(?:new|[a-f0-9]{32})(?:\/attendees)?)?$/.test(value)) return value;
  return role === "organizer" ? "#studio" : "#my-events";
}

async function signIn(email, password, role, next = "") {
  const result = await api("/session", "POST", {email, password, role});
  state.user = result.user;
  message("");
  return go(safeNext(next, state.user.role));
}

function confirmAction(title, description, label) {
  document.querySelector("#confirm-title").textContent = title;
  document.querySelector("#confirm-description").textContent = description;
  document.querySelector("#confirm-action").textContent = label;
  dialog.returnValue = "";
  return new Promise(resolve => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once: true});
    dialog.showModal();
  });
}

const confirmations = {
  "cancel-registration": ["Cancel your registration?", "Your seat will become available to another student.", "Cancel registration"],
  "cancel-event": ["Cancel this event?", "Students will see the cancellation in My events. Their registration history stays available.", "Cancel event"],
  "archive-event": ["Archive this event?", "The event will be removed from public listings and kept in your archive.", "Archive event"],
};

async function handleAction(control) {
  const {action: command, id, version, registrationId} = control.dataset;
  if (command === "logout") {
    await api("/session", "DELETE");
    state.user = null;
    message("You’re signed out.");
    return go("#home");
  }
  if (preview && (command === "demo-student" || command === "demo-organizer")) {
    const role = command === "demo-student" ? "student" : "organizer";
    return signIn(preview.accounts[role].email, preview.password, role);
  }
  const prompt = confirmations[command];
  if (!prompt || dialog.open || !(await confirmAction(...prompt))) return;
  const encoded = encodeURIComponent(id);
  if (command === "cancel-registration") {
    await api("/events/" + encoded + "/registration", "DELETE", {registration_id: registrationId});
    message("Your registration was cancelled.");
  } else {
    const cancel = command === "cancel-event";
    await api("/organizer/events/" + encoded + (cancel ? "/cancel" : ""), cancel ? "POST" : "DELETE", {version: Number(version)});
    message(cancel ? "Event cancelled." : "Event archived.");
  }
  return render({focus: true});
}

document.addEventListener("click", async event => {
  if (event.target.closest("a.skip")) {
    event.preventDefault();
    main.focus();
    return;
  }
  const control = event.target.closest("button[data-action]");
  if (!control || control.disabled) return;
  control.disabled = true;
  try {
    await handleAction(control);
  } catch (error) {
    message(error.message, true);
  } finally {
    control.disabled = false;
  }
});

document.addEventListener("submit", async event => {
  const form = event.target;
  if (!["event-filters", "login-form", "register-form", "event-form"].includes(form.id)) return;
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form, event.submitter || undefined));
  if (form.id === "event-filters") return go(exploreLink(data));
  const controls = Array.from(form.querySelectorAll("button[type=submit], button:not([type])"));
  controls.forEach(control => { control.disabled = true; });
  form.querySelector(".form-error").hidden = true;
  try {
    if (form.id === "login-form") {
      await signIn(data.email, data.password, form.dataset.role, form.dataset.next);
    } else if (form.id === "register-form") {
      await api("/events/" + encodeURIComponent(form.dataset.event) + "/registration", "POST", data);
      message("Your registration is confirmed.");
      await go("#my-events");
    } else {
      data.capacity = Number(data.capacity);
      const id = form.dataset.id;
      if (id) data.version = Number(form.dataset.version);
      await api(id ? "/organizer/events/" + encodeURIComponent(id) : "/organizer/events", id ? "PUT" : "POST", data);
      message(data.status === "draft" ? "Draft saved." : id ? "Event updated." : "Event published.");
      await go("#studio");
    }
  } catch (error) {
    displayFormError(form, error);
  } finally {
    controls.forEach(control => { control.disabled = false; });
  }
});

window.addEventListener("hashchange", () => {
  if (initialized) render({focus: true});
});

async function start() {
  if (preview) {
    const banner = document.querySelector("#preview-banner");
    banner.className = "preview-strip";
    banner.hidden = false;
    banner.innerHTML = `<div class="wrap">Review edition · Fictional events · Changes stay in this tab
      <span class="preview-buttons"><button type="button" data-action="demo-student">Try student</button>
      <button type="button" data-action="demo-organizer">Try organizer</button></span></div>`;
  }
  try {
    state = await api("/session");
    initialized = true;
    await render();
  } catch {
    main.innerHTML = empty("CampusLoop couldn’t start", "Check your connection and reload the page.");
  }
}

start();
