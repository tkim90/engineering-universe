const form = document.getElementById("search-form");
const resultsList = document.getElementById("results");
const status = document.getElementById("status");
const queryInput = document.getElementById("query");
const modeSelect = document.getElementById("mode");
const apiBase = window.location.protocol === "file:" ? "http://localhost:8080" : "";
let debounceTimer = null;
let lastRequestId = 0;

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
  status.textContent = `${payload.count} results`;
  payload.results.forEach((item) => {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = item.url || "#";
    link.textContent = item.title || item.doc_id;
    link.target = "_blank";
    li.appendChild(link);
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
