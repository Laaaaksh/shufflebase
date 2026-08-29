let currentSchema = null;

const el = (id) => document.getElementById(id);

function showError(target, message) {
  const box = el(target);
  box.hidden = false;
  box.textContent = message;
}

function hideError(target) {
  el(target).hidden = true;
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.join("\n") : detail || "request failed");
  }
  return data;
}

function keyBadges(column) {
  const badges = [];
  if (column.is_primary_key) badges.push('<span class="badge pk">PK</span>');
  if (column.foreign_key) {
    badges.push(
      `<span class="badge fk">FK &rarr; ${column.foreign_key.table}(${column.foreign_key.columns.join(",")})</span>`
    );
  }
  if (column.is_referenced) badges.push('<span class="badge ref">referenced</span>');
  return badges.join(" ");
}

function renderSchema(schema) {
  const container = el("tables");
  container.innerHTML = "";
  for (const table of schema.tables) {
    const card = document.createElement("div");
    card.className = "table-card";
    card.innerHTML = `
      <h4>${table.name}</h4>
      <table>
        <thead><tr><th>Column</th><th>Type</th><th>Key</th><th>Strategy</th></tr></thead>
        <tbody></tbody>
      </table>
    `;
    const tbody = card.querySelector("tbody");
    for (const column of table.columns) {
      const tr = document.createElement("tr");
      const options = column.allowed_strategies
        .map(
          (s) => `<option value="${s}" ${s === column.suggested_strategy ? "selected" : ""}>${s}</option>`
        )
        .join("");
      tr.innerHTML = `
        <td class="col-name">${column.name}</td>
        <td>${column.type}</td>
        <td>${keyBadges(column)}</td>
        <td><select data-table="${table.name}" data-column="${column.name}">${options}</select></td>
      `;
      tbody.appendChild(tr);
    }
    container.appendChild(card);
  }
  el("schema-panel").hidden = false;
  el("run-panel").hidden = false;
}

function collectStrategies() {
  const tables = {};
  document.querySelectorAll("#tables select").forEach((sel) => {
    const table = sel.dataset.table;
    const column = sel.dataset.column;
    tables[table] = tables[table] || {};
    tables[table][column] = sel.value;
  });
  return tables;
}

el("connect-btn").addEventListener("click", async () => {
  hideError("connect-error");
  const url = el("source-url").value.trim();
  if (!url) return;
  el("connect-btn").disabled = true;
  try {
    currentSchema = await postJSON("/api/introspect", { url });
    renderSchema(currentSchema);
  } catch (err) {
    showError("connect-error", err.message);
  } finally {
    el("connect-btn").disabled = false;
  }
});

el("run-btn").addEventListener("click", async () => {
  hideError("run-error");
  el("run-result").hidden = true;
  const source = el("source-url").value.trim();
  const target = el("target-url").value.trim();
  const seedRaw = el("seed").value.trim();
  if (!target) {
    showError("run-error", "a target database URL is required");
    return;
  }
  const body = {
    source,
    target,
    seed: seedRaw ? parseInt(seedRaw, 10) : null,
    tables: collectStrategies(),
  };
  el("run-btn").disabled = true;
  try {
    const result = await postJSON("/api/run", body);
    const rows = el("result-rows");
    rows.innerHTML = result.tables
      .map((t) => `<tr><td class="col-name">${t.table}</td><td>${t.rows}</td></tr>`)
      .join("");
    const status = el("integrity-status");
    if (result.ok) {
      status.className = "ok";
      status.textContent = `All foreign keys resolve correctly. ${result.total_rows} rows written.`;
    } else {
      status.className = "fail";
      status.textContent = `${result.violations.length} foreign key violation(s):\n` + result.violations.join("\n");
    }
    el("run-result").hidden = false;
  } catch (err) {
    showError("run-error", err.message);
  } finally {
    el("run-btn").disabled = false;
  }
});
