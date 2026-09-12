/* ==========================================================================
 * Campus Event Recommendation System - frontend logic
 *
 * Plain JavaScript, no build step and no framework. The page talks to the
 * FastAPI backend over fetch() and renders event cards.
 *
 * The API base URL is resolved in this order:
 *   1. ?api=http://host:port    (query parameter, handy for demos)
 *   2. the origin the page is served from, when that is the API itself
 *   3. http://127.0.0.1:8000    (fallback when opening index.html as a file)
 * ========================================================================== */

(() => {
  "use strict";

  // ---------------------------------------------------------------- config
  const params = new URLSearchParams(window.location.search);

  const API_BASE = (() => {
    const override = params.get("api");
    if (override) return override.replace(/\/+$/, "");
    if (window.location.protocol.startsWith("http")) return window.location.origin;
    return "http://127.0.0.1:8000";
  })();

  const RESULT_LIMIT = 30;

  // ------------------------------------------------------------------ dom
  const $ = (id) => document.getElementById(id);

  const el = {
    apiStatus: $("api-status"),
    studentSelect: $("student-select"),
    profile: $("student-profile"),
    pFaculty: $("p-faculty"),
    pYear: $("p-year"),
    pTime: $("p-time"),
    pPrice: $("p-price"),
    pInterests: $("p-interests"),
    filterCategory: $("filter-category"),
    filterDate: $("filter-date"),
    filterFree: $("filter-free"),
    clearFilters: $("clear-filters"),
    tabs: Array.from(document.querySelectorAll(".tab")),
    resultsHeading: $("results-heading"),
    resultsCount: $("results-count"),
    loading: $("state-loading"),
    error: $("state-error"),
    errorMessage: $("error-message"),
    empty: $("state-empty"),
    retry: $("retry-btn"),
    cards: $("cards"),
  };

  // ---------------------------------------------------------------- state
  const state = {
    view: "recommendations", // "recommendations" | "events"
    studentId: params.get("student_id") ? Number(params.get("student_id")) : null,
    students: [],
    requestId: 0, // guards against out-of-order responses
  };

  // ------------------------------------------------------------- utilities
  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));

  async function api(path) {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) { /* response was not JSON - keep the status text */ }
      throw new Error(detail);
    }
    return response.json();
  }

  const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const pad = (n) => String(n).padStart(2, "0");

  function formatDateTime(startISO, endISO) {
    const start = new Date(startISO);
    const end = new Date(endISO);
    const day = `${WEEKDAYS[start.getDay()]}, ${start.getDate()} ${MONTHS[start.getMonth()]}`;
    const from = `${pad(start.getHours())}:${pad(start.getMinutes())}`;
    const to = `${pad(end.getHours())}:${pad(end.getMinutes())}`;
    return `${day} · ${from}–${to}`;
  }

  const formatPrice = (price) => (Number(price) === 0 ? "Free" : `${Number(price)} MKD`);

  function formatDistance(km, isOnline) {
    if (isOnline) return "Online";
    if (km === null || km === undefined) return "—";
    return km < 1 ? `${Math.round(km * 1000)} m` : `${Number(km).toFixed(2)} km`;
  }

  const trimSeconds = (t) => (typeof t === "string" ? t.slice(0, 5) : "—");

  // ------------------------------------------------------------ ui helpers
  function showState(which) {
    el.loading.hidden = which !== "loading";
    el.error.hidden = which !== "error";
    el.empty.hidden = which !== "empty";
    el.cards.hidden = which !== "cards";
    if (which !== "cards") el.cards.innerHTML = "";
  }

  function setApiStatus(state_, text) {
    el.apiStatus.dataset.state = state_;
    el.apiStatus.textContent = text;
  }

  function scoreClass(score) {
    if (score >= 80) return "score--high";
    if (score >= 50) return "";
    return "score--low";
  }

  // --------------------------------------------------------------- render
  const BREAKDOWN_LABELS = {
    interest_match: ["Interest", 35],
    time_availability: ["Time", 20],
    audience_match: ["Audience", 15],
    distance: ["Distance", 15],
    price: ["Price", 8],
    capacity: ["Capacity", 7],
  };

  function renderBreakdown(breakdown) {
    if (!breakdown) return "";
    const bars = Object.entries(BREAKDOWN_LABELS)
      .map(([key, [label, max]]) => {
        const value = Number(breakdown[key] ?? 0);
        const pct = Math.max(0, Math.min(100, (value / max) * 100));
        return `
          <div class="bar">
            <span class="bar__key">${label}</span>
            <span class="bar__track"><span class="bar__fill" style="width:${pct.toFixed(0)}%"></span></span>
            <span class="bar__val">${value.toFixed(1)}/${max}</span>
          </div>`;
      })
      .join("");

    return `
      <details class="breakdown">
        <summary>How this score was calculated</summary>
        <div class="bars">${bars}</div>
      </details>`;
  }

  function renderCard(item, { withScore }) {
    const isOnline = Boolean(item.is_online);
    const price = Number(item.price ?? 0);
    const places = item.available_places ?? Math.max((item.capacity ?? 0) - (item.registered_count ?? 0), 0);

    const scoreBlock = withScore
      ? `<div class="score ${scoreClass(item.score)}">
           <span class="score__num">${item.score}</span>
           <span class="score__lbl">score</span>
         </div>`
      : "";

    const reasonBlock = withScore && item.reason
      ? `<p class="reason"><strong>Why:</strong> ${escapeHtml(item.reason)}</p>`
      : "";

    return `
      <li class="card">
        <div class="card__top">
          <div>
            <h3 class="card__title">${escapeHtml(item.title)}</h3>
            <div class="card__meta">
              <span class="tag tag--cat">${escapeHtml(item.category)}</span>
              ${price === 0 ? '<span class="tag tag--free">Free</span>' : ""}
              ${isOnline ? '<span class="tag tag--online">Online</span>' : ""}
              <span class="tag">${escapeHtml(item.target_audience ?? "All Students")}</span>
            </div>
          </div>
          ${scoreBlock}
        </div>

        <div class="details">
          <div class="detail">
            <span class="detail__key">When</span>
            <span class="detail__val">${formatDateTime(item.start_datetime, item.end_datetime)}</span>
          </div>
          <div class="detail">
            <span class="detail__key">Where</span>
            <span class="detail__val">${escapeHtml(item.location_name)}</span>
          </div>
          <div class="detail">
            <span class="detail__key">Distance</span>
            <span class="detail__val">${formatDistance(item.distance_km, isOnline)}</span>
          </div>
          <div class="detail">
            <span class="detail__key">Organizer</span>
            <span class="detail__val">${escapeHtml(item.organizer)}</span>
          </div>
          <div class="detail">
            <span class="detail__key">Price</span>
            <span class="detail__val">${formatPrice(price)}</span>
          </div>
          <div class="detail">
            <span class="detail__key">Places left</span>
            <span class="detail__val">${places}</span>
          </div>
        </div>

        ${reasonBlock}
        ${withScore ? renderBreakdown(item.score_breakdown) : ""}
      </li>`;
  }

  function renderCards(items, { withScore }) {
    if (!items.length) {
      showState("empty");
      return;
    }
    el.cards.innerHTML = items.map((item) => renderCard(item, { withScore })).join("");
    showState("cards");
  }

  // ------------------------------------------------------------- loaders
  async function loadStudents() {
    const students = await api("/students?limit=500");
    state.students = students;

    el.studentSelect.innerHTML = students
      .map((s) => `<option value="${s.id}">${escapeHtml(`${s.id} · ${s.name} — ${s.faculty}`)}</option>`)
      .join("");

    const known = students.some((s) => s.id === state.studentId);
    if (!known) state.studentId = students.length ? students[0].id : null;
    if (state.studentId !== null) el.studentSelect.value = String(state.studentId);

    renderProfile();
  }

  async function loadCategories() {
    const categories = await api("/events/categories");
    el.filterCategory.innerHTML =
      '<option value="">All categories</option>' +
      categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  }

  function renderProfile() {
    const student = state.students.find((s) => s.id === state.studentId);
    if (!student) {
      el.profile.hidden = true;
      return;
    }
    el.pFaculty.textContent = student.faculty;
    el.pYear.textContent = `Year ${student.year_of_study}`;
    el.pTime.textContent = `${trimSeconds(student.available_from)} – ${trimSeconds(student.available_to)}`;
    el.pPrice.textContent = formatPrice(student.max_price);
    el.pInterests.innerHTML = (student.interests || [])
      .map((i) => `<span class="chip">${escapeHtml(i)}</span>`)
      .join("");
    el.profile.hidden = false;
  }

  function buildQuery() {
    const query = new URLSearchParams();
    const category = el.filterCategory.value.trim();
    const date = el.filterDate.value;
    const free = el.filterFree.checked;

    if (category) query.set("category", category);
    if (free) query.set("free_only", "true");

    if (state.view === "recommendations") {
      query.set("limit", String(RESULT_LIMIT));
      // The date filter is applied client-side for recommendations, so the
      // ranking is still computed over the student's full candidate list.
      return { query, clientDate: date || null };
    }

    if (date) query.set("date", date);
    query.set("upcoming_only", "true");
    query.set("limit", String(RESULT_LIMIT));
    return { query, clientDate: null };
  }

  async function loadResults() {
    const requestId = ++state.requestId;
    showState("loading");

    const { query, clientDate } = buildQuery();

    try {
      let items;

      if (state.view === "recommendations") {
        if (state.studentId === null) {
          showState("empty");
          return;
        }
        const data = await api(`/recommendations/${state.studentId}?${query}`);
        if (requestId !== state.requestId) return; // a newer request won
        items = data.recommendations;
        if (clientDate) {
          items = items.filter((i) => i.start_datetime.slice(0, 10) === clientDate);
        }
        el.resultsHeading.textContent = `Recommended for ${data.student_name ?? "you"}`;
        el.resultsCount.textContent =
          `${items.length} shown · ${data.total_candidates} events matched the basic criteria`;
        renderCards(items, { withScore: true });
      } else {
        items = await api(`/events?${query}`);
        if (requestId !== state.requestId) return;
        el.resultsHeading.textContent = "All upcoming events";
        el.resultsCount.textContent = `${items.length} event${items.length === 1 ? "" : "s"}`;
        renderCards(items, { withScore: false });
      }
    } catch (err) {
      if (requestId !== state.requestId) return;
      el.errorMessage.textContent = err.message || "Unknown error";
      el.resultsCount.textContent = "";
      showState("error");
    }
  }

  // -------------------------------------------------------------- events
  function syncUrl() {
    const url = new URL(window.location.href);
    if (state.studentId !== null) url.searchParams.set("student_id", String(state.studentId));
    window.history.replaceState({}, "", url);
  }

  el.studentSelect.addEventListener("change", () => {
    state.studentId = Number(el.studentSelect.value);
    renderProfile();
    syncUrl();
    loadResults();
  });

  [el.filterCategory, el.filterDate, el.filterFree].forEach((control) => {
    control.addEventListener("change", loadResults);
  });

  el.clearFilters.addEventListener("click", () => {
    el.filterCategory.value = "";
    el.filterDate.value = "";
    el.filterFree.checked = false;
    loadResults();
  });

  el.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      if (tab.dataset.view === state.view) return;
      state.view = tab.dataset.view;
      el.tabs.forEach((t) => {
        const active = t === tab;
        t.classList.toggle("is-active", active);
        t.setAttribute("aria-selected", String(active));
      });
      loadResults();
    });
  });

  el.retry.addEventListener("click", init);

  // ----------------------------------------------------------------- boot
  async function init() {
    showState("loading");
    setApiStatus("checking", "Connecting…");

    try {
      await api("/health");
      setApiStatus("ok", "API online");
    } catch (err) {
      setApiStatus("down", "API offline");
      el.errorMessage.textContent =
        `Cannot reach the API at ${API_BASE}. Start it with ` +
        `"uv run uvicorn app.main:app --reload" and reload this page.`;
      showState("error");
      return;
    }

    try {
      await Promise.all([loadStudents(), loadCategories()]);
      syncUrl();
      await loadResults();
    } catch (err) {
      el.errorMessage.textContent = err.message || "Unknown error";
      showState("error");
    }
  }

  init();
})();
