const form = document.getElementById("search-form");
const resultsList = document.getElementById("results");
const status = document.getElementById("status");
const queryInput = document.getElementById("query");
const modeSelect = document.getElementById("mode");
const apiBase = window.location.protocol === "file:" ? "http://localhost:8080" : "";
let debounceTimer = null;
let lastRequestId = 0;

const formatAuthors = (authors) => {
  if (Array.isArray(authors)) {
    return authors.length ? authors.join(", ") : "Unknown";
  }
  if (typeof authors === "string") {
    const parts = authors
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return parts.length ? parts.join(", ") : "Unknown";
  }
  return "Unknown";
};

const formatDate = (value) => {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
  return value;
};

const runSearch = async () => {
  const query = queryInput.value.trim();
  const mode = modeSelect.value;
  if (!query) {
    status.textContent = "Enter a query to search.";
    resultsList.innerHTML = "";
    return;
  }
  const requestId = ++lastRequestId;
  status.textContent = "Searching...";
  resultsList.innerHTML = "";
  const response = await fetch(
    `${apiBase}/search?q=${encodeURIComponent(query)}&mode=${mode}`
  );
  if (!response.ok) {
    status.textContent = "Search failed.";
    return;
  }
  const payload = await response.json();
  if (requestId !== lastRequestId) {
    return;
  }
  const duration =
    typeof payload.duration_ms === "number"
      ? ` · ${payload.duration_ms} ms`
      : "";
  status.textContent = `${payload.count} results${duration}`;
  payload.results.forEach((item) => {
    const li = document.createElement("li");
    li.className = "result";
    const link = document.createElement("a");
    link.href = item.url || "#";
    link.textContent = item.title || item.doc_id;
    link.target = "_blank";
    link.className = "result__title";
    const meta = document.createElement("div");
    meta.className = "result__meta";
    meta.textContent = `Author: ${formatAuthors(item.authors)} · Date: ${formatDate(
      item.published_at
    )} · Company: ${item.company || "Unknown"}`;
    const snippet = document.createElement("p");
    snippet.className = "result__snippet";
    snippet.textContent = item.snippet || "";
    li.appendChild(link);
    li.appendChild(meta);
    if (snippet.textContent) {
      li.appendChild(snippet);
    }
    resultsList.appendChild(li);
  });
};

const scheduleSearch = () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(runSearch, 200);
};

form.addEventListener("submit", (event) => {
  event.preventDefault();
  scheduleSearch();
});

queryInput.addEventListener("input", scheduleSearch);
modeSelect.addEventListener("change", scheduleSearch);
