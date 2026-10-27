const $ = (selector) => document.querySelector(selector);

function render(target, items, source) {
  $(source).textContent = items.length ? `数据来源：${items[0].source || "seekdb"}` : "";
  $(target).innerHTML = items.map((item) => `
    <li>
      <h3>${item.title || item.note_id}</h3>
      <p>${item.snippet || ""}</p>
      <p><span class="badge">${item.score ?? "memory"}</span>${(item.tags || []).join(" · ")}</p>
    </li>`).join("");
}

$("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/search", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query: $("#query").value, limit: 5})
  });
  const data = await response.json();
  render("#results", data.results, "#search-source");
  $("#search-source").textContent = `数据来源：${data.source}`;
});

$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/profile", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      user_id: $("#user").value,
      interests: $("#interests").value.split(",").map((item) => item.trim()).filter(Boolean),
      stage: $("#stage").value,
      goal: $("#goal").value
    })
  });
  const data = await response.json();
  $("#profile-source").textContent = `已写入 PowerContext：${data.source}`;
});

$("#recommend-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch(`/api/recommend/${encodeURIComponent($("#recommend-user").value)}`);
  const data = await response.json();
  render("#recommendations", data.results, "#recommend-source");
  $("#recommend-source").textContent = `记忆读取：${data.sources.memory} · 检索：${data.sources.notes}`;
});
