(() => {
  "use strict";

  const fixture = CAMPUSLOOP_REVIEW_DATA;
  const day = 24 * 60 * 60 * 1000;
  const elapsed = Math.max(0, Math.floor((Date.now() - fixture.generated_at) / day)) * day;
  const events = new Map(fixture.events.map(event => {
    const shifted = {...event};
    for (const field of ["starts_at", "ends_at", "closes_at"]) {
      shifted[field] = new Date(Date.parse(event[field]) + elapsed).toISOString();
    }
    return [event.id, shifted];
  }));
  const registrations = new Map();
  const accounts = fixture.accounts;
  let user = null;
  let sequence = 1000;

  function fail(status, message) {
    const error = new Error(message);
    error.status = status;
    throw error;
  }

  function requireRole(role) {
    if (!user) fail(401, "Sign in to continue.");
    if (user.role !== role) fail(403, "This account cannot access that area.");
  }

  function eventView(event) {
    const now = Date.now();
    const registration = registrations.get(event.id);
    const active = registration && !registration.cancelled_at ? 1 : 0;
    const seats = event.capacity - active;
    let state = event.status;
    if (state === "published") {
      if (Date.parse(event.ends_at) <= now) state = "completed";
      else if (Date.parse(event.starts_at) <= now) state = "ongoing";
      else if (Date.parse(event.closes_at) <= now) state = "closed";
      else state = seats > 0 ? "open" : "full";
    }
    const labels = {draft: "Draft", cancelled: "Cancelled", archived: "Archived", open: "Open",
      full: "Full", closed: "Registration closed", ongoing: "In progress", completed: "Completed"};
    return {...event, state, state_label: labels[state], registrations: active, seats_left: seats};
  }

  function listing(url) {
    const category = url.searchParams.get("category");
    const keyword = (url.searchParams.get("q") || "").trim().toLowerCase();
    const status = url.searchParams.get("status") || "upcoming";
    const order = url.searchParams.get("order") || "soon";
    const page = Number(url.searchParams.get("page")) || 1;
    const matches = [...events.values()].map(eventView).filter(event => {
      if (!["published", "cancelled"].includes(event.status)) return false;
      if (category && event.category !== category) return false;
      if (keyword && ![event.title, event.organizer, event.venue, event.description]
        .join(" ").toLowerCase().includes(keyword)) return false;
      if (status === "open") return event.state === "open";
      if (status === "upcoming") return event.status === "published" && event.state !== "completed";
      if (status === "past") return ["completed", "cancelled"].includes(event.state);
      return true;
    });
    matches.sort((a, b) => order === "deadline" ? a.closes_at.localeCompare(b.closes_at) :
      (order === "latest" ? -1 : 1) * a.starts_at.localeCompare(b.starts_at));
    return {events: matches.slice((page - 1) * 12, page * 12), page, total: matches.length,
      pages: Math.max(1, Math.ceil(matches.length / 12))};
  }

  function saveEvent(data, existing) {
    const dates = {};
    for (const key of ["starts_at", "ends_at", "closes_at"]) {
      const date = new Date(data[key] + ":00+05:30");
      if (!Number.isFinite(date.getTime())) fail(422, "Enter valid campus-local dates.");
      dates[key] = date.toISOString();
    }
    if (dates.ends_at <= dates.starts_at || dates.closes_at > dates.starts_at) {
      fail(422, "Check the event and registration dates.");
    }
    if (!Number.isInteger(data.capacity) || data.capacity < 1 || data.capacity > 5000) {
      fail(422, "Capacity must be between 1 and 5,000.");
    }
    if (data.status === "published" && existing?.status !== "published" && Date.parse(dates.closes_at) <= Date.now()) {
      fail(422, "Set a future deadline to publish.");
    }
    if (existing && data.capacity < eventView(existing).registrations) fail(409, "Capacity is below registrations.");
    sequence += 1;
    const id = existing?.id || sequence.toString(16).padStart(32, "0");
    const event = {...data, ...dates, id, version: (existing?.version || 0) + 1};
    events.set(id, event);
    return {event: eventView(event)};
  }

  function publicEvents(parts, url, method, data) {
    const [, id, section] = parts;
    if (!id) return listing(url);
    const event = events.get(id);
    const prior = user?.role === "student" ? registrations.get(id) : null;
    if (!event || (event.status === "draft" && user?.role !== "organizer") ||
        (event.status === "archived" && !prior && user?.role !== "organizer")) fail(404, "Event not found.");
    if (!section) return {event: eventView(event), registration: prior || null};
    requireRole("student");
    if (method === "POST") {
      if (eventView(event).state !== "open" || (prior && !prior.cancelled_at)) fail(409, "Registration is not available.");
      const registration = {...data, id: (++sequence).toString(16).padEnd(32, "0"), event_id: id,
        registered_at: new Date().toISOString(), cancelled_at: null};
      registrations.set(id, registration);
      return {registration};
    }
    if (!prior) fail(404, "Registration not found.");
    if (data.registration_id && data.registration_id !== prior.id) {
      fail(409, "This registration changed. Reopen My events before cancelling.");
    }
    if (prior.cancelled_at) return {cancelled: true};
    if (Date.parse(event.starts_at) <= Date.now()) fail(409, "This event has already started.");
    prior.cancelled_at ||= new Date().toISOString();
    return {cancelled: true};
  }

  function studio(parts, method, data) {
    requireRole("organizer");
    const [, , id, section] = parts;
    if (!id) return method === "POST" ? saveEvent(data) : {events: [...events.values()].map(eventView)};
    const event = events.get(id);
    if (!event) fail(404, "Event not found.");
    if (section === "attendees") {
      const record = registrations.get(id);
      return {event: eventView(event), items: record ? [{...record, name: accounts.student.name, email: accounts.student.email}] : []};
    }
    if (method === "GET") return {event: eventView(event)};
    if (data.version !== event.version) fail(409, "This event changed. Reopen it before saving.");
    if (method === "PUT") {
      if (event.status === "cancelled" || event.status === "archived" ||
          (event.status === "published" && Date.parse(event.starts_at) <= Date.now())) {
        fail(409, "This event is read-only.");
      }
      return saveEvent(data, event);
    }
    event.status = method === "DELETE" ? "archived" : "cancelled";
    event.version += 1;
    return {};
  }

  async function request(path, method, data) {
    const url = new URL(path, "https://review.campusloop.example");
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "session") {
      if (method === "DELETE") user = null;
      if (method === "POST") {
        const match = Object.values(accounts).find(account => account.email === data.email.trim().toLowerCase());
        if (!match || data.password !== fixture.password) fail(401, "Choose one of the fictional review accounts.");
        if (data.role && match.role !== data.role) {
          fail(403, "This account belongs to the other sign-in. Switch sign-in and try again.");
        }
        user = match;
      }
      return {user, timezone: fixture.timezone};
    }
    if (parts[0] === "events") return publicEvents(parts, url, method, data);
    if (parts[0] === "my-events") {
      requireRole("student");
      return {items: [...registrations].map(([id, registration]) => ({event: eventView(events.get(id)), registration}))};
    }
    if (parts[0] === "organizer") return studio(parts, method, data);
    fail(404, "Page not found.");
  }

  const hero = document.getElementById("review-hero")?.getAttribute("src");
  window.campusloopPreview = {accounts, password: fixture.password, hero, request};
})();
