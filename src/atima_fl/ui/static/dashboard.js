"use strict";
/* ATIMA dashboard — strictly read-only views of existing workspace and plugin APIs.
 * Nothing here starts a training job or fabricates run metadata.
 */
(function(){
  const get = id => document.getElementById(id);
  let requestNumber = 0;
  function text(id, value) {
    const el = get(id);
    if (el) el.textContent = String(value);
  }
  async function json(path) {
    const response = await fetch(path, {headers: {"Accept": "application/json"}});
    if (!response.ok) throw new Error("Dashboard API " + path + ": HTTP " + response.status);
    return response.json();
  }
  function emptyRow(message) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = message;
    row.append(cell);
    return row;
  }
  function runRow(run) {
    const row = document.createElement("tr");
    const cells = [
      run.id || "—",
      run.config?.attack || "—",
      run.config?.dataset || "—",
      Number.isInteger(run.config?.clients) ? run.config.clients : "—",
      run.status || "unknown",
      typeof run.updated_at === "string" && !Number.isNaN(Date.parse(run.updated_at))
        ? run.updated_at.slice(0, 10) : "—"
    ];
    for (let i = 0; i < cells.length; i++) {
      const cell = document.createElement("td");
      if (i === 0) {
        const link = document.createElement("button");
        link.type = "button";
        link.className = "dash-run-link";
        link.textContent = String(cells[i]);
        link.addEventListener("click", () => navigateTo("results", true));
        cell.append(link);
      } else if (i === 4) {
        const dot = document.createElement("span");
        dot.className = "dash-status-dot " +
          (cells[i] === "complete" ? "complete" :
           cells[i] === "failed" ? "failed" :
           cells[i] === "running" ? "running" : "");
        dot.setAttribute("aria-hidden", "true");
        cell.append(dot, document.createTextNode(String(cells[i])));
      } else {
        cell.textContent = String(cells[i]);
      }
      row.append(cell);
    }
    return row;
  }
  function renderRuns(values) {
    const body = get("dash-recent-body");
    if (!body) return;
    body.replaceChildren();
    if (!Array.isArray(values)) {
      body.append(emptyRow("Results are currently unavailable."));
      text("dash-recent-status", "Could not read the local results catalog.");
      return;
    }
    // Use the manifest modification time actually recorded on disk, never the run ID as a date.
    const ordered = [...values].sort((a, b) =>
      (Date.parse(b.updated_at || "") || 0) - (Date.parse(a.updated_at || "") || 0) ||
      String(b.id || "").localeCompare(String(a.id || "")));
    for (const run of ordered.slice(0, 4)) body.append(runRow(run));
    if (!values.length) body.append(emptyRow("No imported experiments yet. Create an experiment to begin."));
    text("dash-recent-status", values.length
      ? "Showing " + Math.min(values.length, 4) + " of " + values.length + " local workspace runs (newest manifest first)."
      : "Only completed/imported workspace evidence appears here; sample rows are not invented.");
  }
  async function refreshDashboard() {
    const sequence = ++requestNumber;
    const [catalogResult, defaultsResult, resultsResult] = await Promise.allSettled([
      json("/api/catalog"), json("/api/defaults"), json("/api/results")
    ]);
    if (sequence !== requestNumber) return;
    if (catalogResult.status === "fulfilled") {
      const c = catalogResult.value.catalog || {};
      text("dash-datasets", c.dataset?.length ?? "—");
      text("dash-attacks", Array.isArray(c.attack)
        ? c.attack.filter(plugin => plugin.id !== "none").length : "—");
      text("dash-aggregators", c.aggregator?.length ?? "—");
    }
    if (defaultsResult.status === "fulfilled") {
      text("dash-clients", defaultsResult.value.clients ?? "—");
    }
    renderRuns(resultsResult.status === "fulfilled" ? resultsResult.value : null);
    text("dash-health", catalogResult.status === "fulfilled" ? "Studio ready" : "Catalog unavailable");
    const health = get("dash-health");
    if (health) health.dataset.ready = String(catalogResult.status === "fulfilled");
  }
  // Shortcut links to existing screens; the catalog search is filtered by actual kind.
  document.querySelectorAll("[data-catalog-focus]").forEach(button => {
    button.addEventListener("click", () => {
      const field = get("component-search");
      if (!field) return;
      field.dataset.kind = button.dataset.catalogFocus;
      field.value = "";
      if (typeof renderComponentCatalog === "function" && typeof catalog !== "undefined" && catalog)
        renderComponentCatalog();
    });
  });
  // Main navigation can target an existing field, without adding new backend APIs.
  document.querySelectorAll("[data-scroll-target]").forEach(button => {
    button.addEventListener("click", () => {
      window.requestAnimationFrame(() => {
        get(button.dataset.scrollTarget)?.scrollIntoView({block: "center", behavior: "smooth"});
      });
    });
  });
  get("dash-settings-theme")?.addEventListener("click", () => get("theme-toggle")?.click());
  document.addEventListener("atima:navigate", event => {
    if (event.detail?.page === "dashboard") refreshDashboard();
  });
  refreshDashboard();
})();
