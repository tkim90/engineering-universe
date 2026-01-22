const form = document.getElementById("search-form");
const resultsList = document.getElementById("results");
const status = document.getElementById("status");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.getElementById("query").value.trim();
  const mode = document.getElementById("mode").value;
  if (!query) {
    status.textContent = "Enter a query to search.";
    return;
  }
  status.textContent = "Searching...";
  resultsList.innerHTML = "";
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&mode=${mode}`);
  const payload = await response.json();
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
});
