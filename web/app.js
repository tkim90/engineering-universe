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

const escapeRegExp = (value) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const tokenizeQuery = (query) =>
  query
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean);

const buildHighlightedText = (text, tokens) => {
  const fragment = document.createDocumentFragment();
  if (!text) {
    return fragment;
  }
  if (!tokens.length) {
    fragment.appendChild(document.createTextNode(text));
    return fragment;
  }
  const pattern = new RegExp(
    `(${tokens.map((token) => escapeRegExp(token)).join("|")})`,
    "gi"
  );
  let lastIndex = 0;
  let match = null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      fragment.appendChild(
        document.createTextNode(text.slice(lastIndex, match.index))
      );
    }
    const mark = document.createElement("mark");
    mark.className = "highlight";
    mark.textContent = match[0];
    fragment.appendChild(mark);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
  return fragment;
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
  const shouldHighlight = mode === "keyword";
  const highlightTokens = shouldHighlight ? tokenizeQuery(query) : [];
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
    const titleText = item.title || item.doc_id || "";
    if (shouldHighlight) {
      link.replaceChildren(buildHighlightedText(titleText, highlightTokens));
    } else {
      link.textContent = titleText;
    }
    link.target = "_blank";
    link.className = "result__title";
    const meta = document.createElement("div");
    meta.className = "result__meta";
    const company = document.createElement("span");
    company.className = "result__company";
    company.textContent = `Company: ${item.company || "Unknown"}`;
    const author = document.createElement("span");
    author.className = "result__author";
    author.textContent = `Author: ${formatAuthors(item.authors)}`;
    const date = document.createElement("span");
    date.className = "result__date";
    date.textContent = `Date: ${formatDate(item.published_at)}`;
    meta.appendChild(company);
    meta.append(" · ");
    meta.appendChild(author);
    meta.append(" · ");
    meta.appendChild(date);
    const snippet = document.createElement("p");
    snippet.className = "result__snippet";
    const snippetText = item.snippet || "";
    if (snippetText) {
      if (shouldHighlight) {
        snippet.replaceChildren(
          buildHighlightedText(snippetText, highlightTokens)
        );
      } else {
        snippet.textContent = snippetText;
      }
    }
    li.appendChild(link);
    li.appendChild(meta);
    if (snippetText) {
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
