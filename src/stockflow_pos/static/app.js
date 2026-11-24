const state = {
  token: localStorage.getItem("pos_token"),
  user: JSON.parse(localStorage.getItem("pos_user") || "null"),
  products: [],
  cart: new Map(),
};

const $ = (sel) => document.querySelector(sel);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMoney(val) {
  return `S/ ${Number(val).toFixed(2)}`;
}

function showToast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.classList.add("hidden"), 3200);
}

async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    logout();
    throw new Error("Sesión expirada. Inicia sesión nuevamente.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Error HTTP ${res.status}`);
  }
  return res;
}

function logout() {
  state.token = null;
  state.user = null;
  state.cart.clear();
  localStorage.removeItem("pos_token");
  localStorage.removeItem("pos_user");
  $("#app-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

async function initApp() {
  if (!state.token || !state.user) {
    $("#login-view").classList.remove("hidden");
    $("#app-view").classList.add("hidden");
    return;
  }

  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#user-badge").textContent = `${state.user.full_name} (${state.user.role})`;

  const isAdmin = state.user.role === "admin";
  $("#admin-product-card").classList.toggle("hidden", !isAdmin);
  $("#csv-non-admin-note").classList.toggle("hidden", isAdmin);
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", !isAdmin);
  });

  await Promise.all([refreshDashboard(), refreshProducts(), refreshCash(), refreshSales()]);
}

async function refreshDashboard() {
  const data = await (await apiFetch("/api/v1/dashboard")).json();
  $("#kpi-today-revenue").textContent = formatMoney(data.today_revenue);
  $("#kpi-today-count").textContent = `${data.today_sales_count} comprobante(s)`;
  $("#kpi-low-stock").textContent = data.low_stock_count;
  $("#kpi-expiring").textContent = data.expiring_count;
  $("#kpi-cash-status").textContent = data.has_open_cash_session ? "Abierta" : "Cerrada";
}

async function refreshProducts() {
  const search = $("#pos-search").value.trim();
  const lowOnly = $("#filter-low-stock").checked;
  const qs = new URLSearchParams();
  if (search) qs.set("search", search);
  const allProducts = await (await apiFetch(`/api/v1/products?${qs.toString()}`)).json();
  state.products = allProducts;

  renderCatalog(allProducts);
  const invList = lowOnly ? allProducts.filter((p) => p.is_low_stock) : allProducts;
  renderInventoryTable(invList);
}

function renderCatalog(products) {
  const container = $("#pos-catalog");
  container.innerHTML = "";
  if (!products.length) {
    container.innerHTML = `<p class="muted">No se encontraron productos.</p>`;
    return;
  }
  products.forEach((p) => {
    const tile = document.createElement("div");
    tile.className = "product-tile";
    tile.innerHTML = `
      <strong>${escapeHtml(p.name)}</strong>
      <span class="meta">${escapeHtml(p.sku)} · ${escapeHtml(p.category)}</span>
      <span class="price">${formatMoney(p.unit_price)}</span>
      <span class="meta">Stock: <strong>${Number(p.stock)}</strong></span>
      <button class="btn btn-primary" ${p.stock <= 0 ? "disabled" : ""}>+ Agregar</button>
    `;
    tile.querySelector("button").addEventListener("click", () => addToCart(p));
    container.appendChild(tile);
  });
}

function addToCart(product) {
  const existing = state.cart.get(product.id);
  const nextQty = (existing ? existing.quantity : 0) + 1;
  if (nextQty > product.stock) {
    showToast(`Stock máximo alcanzado para ${product.name} (${product.stock}).`);
    return;
  }
  state.cart.set(product.id, { product, quantity: nextQty });
  renderCart();
}

function renderCart() {
  const container = $("#cart-items");
  container.innerHTML = "";
  let total = 0;

  if (!state.cart.size) {
    container.innerHTML = `<p class="muted">Agrega productos del catálogo para iniciar una venta.</p>`;
  } else {
    state.cart.forEach(({ product, quantity }) => {
      const lineTotal = Number(product.unit_price) * quantity;
      total += lineTotal;
      const row = document.createElement("div");
      row.className = "cart-row";
      row.innerHTML = `
        <div>
          <strong>${escapeHtml(product.name)}</strong>
          <div class="muted">${formatMoney(product.unit_price)} × ${Number(quantity)}</div>
        </div>
        <div class="cart-controls">
          <span>${formatMoney(lineTotal)}</span>
          <button type="button" class="btn btn-ghost" data-op="-">-</button>
          <button type="button" class="btn btn-ghost" data-op="+">+</button>
        </div>
      `;
      row.querySelector('[data-op="-"]').addEventListener("click", () => {
        if (quantity <= 1) state.cart.delete(product.id);
        else state.cart.set(product.id, { product, quantity: quantity - 1 });
        renderCart();
      });
      row.querySelector('[data-op="+"]').addEventListener("click", () => addToCart(product));
      container.appendChild(row);
    });
  }

  const subtotal = total / 1.18;
  const igv = total - subtotal;
  $("#cart-subtotal").textContent = formatMoney(subtotal);
  $("#cart-igv").textContent = formatMoney(igv);
  $("#cart-total").textContent = formatMoney(total);
}

function renderInventoryTable(products) {
  const tbody = $("#inventory-tbody");
  tbody.innerHTML = "";
  const isAdmin = state.user?.role === "admin";

  products.forEach((p) => {
    const badges = [];
    if (p.is_low_stock) badges.push(`<span class="badge badge-warn">Stock bajo</span>`);
    if (p.expiry_status === "expired") badges.push(`<span class="badge badge-danger">Vencido</span>`);
    else if (p.expiry_status === "expiring_soon") badges.push(`<span class="badge badge-warn">Por vencer</span>`);
    if (!badges.length) badges.push(`<span class="badge badge-ok">OK</span>`);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.sku)}</td>
      <td><strong>${escapeHtml(p.name)}</strong></td>
      <td>${escapeHtml(p.category)}</td>
      <td>${formatMoney(p.unit_price)}</td>
      <td>${Number(p.stock)} <span class="muted">(mín. ${Number(p.min_stock)})</span></td>
      <td>${escapeHtml(p.expires_at || "—")}</td>
      <td>${badges.join(" ")}</td>
      ${isAdmin ? `<td><button class="btn btn-ghost btn-restock">+10 u.</button></td>` : ""}
    `;
    if (isAdmin) {
      tr.querySelector(".btn-restock").addEventListener("click", async () => {
        try {
          await apiFetch(`/api/v1/products/${p.id}/restock`, {
            method: "PATCH",
            body: JSON.stringify({ quantity: 10 }),
          });
          showToast(`Se repusieron +10 unidades a ${p.name}.`);
          await Promise.all([refreshProducts(), refreshDashboard()]);
        } catch (err) {
          showToast(err.message);
        }
      });
    }
    tbody.appendChild(tr);
  });
}

async function refreshCash() {
  const session = await (await apiFetch("/api/v1/cash/current")).json();
  const statusBox = $("#cash-status-box");
  if (session) {
    statusBox.innerHTML = `Caja <strong>ABIERTA</strong> desde ${new Date(session.opened_at).toLocaleString()} · Monto inicial: <strong>${formatMoney(session.opening_amount)}</strong>`;
    $("#open-cash-form").classList.add("hidden");
    $("#close-cash-form").classList.remove("hidden");
  } else {
    statusBox.innerHTML = `No hay una sesión de caja abierta actualmente.`;
    $("#open-cash-form").classList.remove("hidden");
    $("#close-cash-form").classList.add("hidden");
  }
}

async function refreshSales() {
  const sales = await (await apiFetch("/api/v1/sales")).json();
  const tbody = $("#sales-tbody");
  tbody.innerHTML = "";
  sales.forEach((s) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(s.receipt_number)}</strong></td>
      <td>${escapeHtml(s.customer_name)}</td>
      <td>${escapeHtml(s.payment_method)}</td>
      <td>${formatMoney(s.subtotal)}</td>
      <td>${formatMoney(s.igv)}</td>
      <td><strong>${formatMoney(s.total)}</strong></td>
    `;
    tbody.appendChild(tr);
  });
}

function showReceipt(sale) {
  const itemsHtml = sale.items
    .map(
      (i) =>
        `<div style="display:flex;justify-content:space-between;font-size:0.9rem;"><span>${Number(i.quantity)}x ${escapeHtml(i.product_name)}</span><span>${formatMoney(i.line_total)}</span></div>`
    )
    .join("");
  $("#receipt-content").innerHTML = `
    <h3 style="margin:0 0 0.25rem;">StockFlow POS — Boleta Simulada</h3>
    <p style="margin:0 0 0.75rem;font-size:0.85rem;color:#475569;">Comprobante: <strong>${escapeHtml(sale.receipt_number)}</strong><br/>Cliente: ${escapeHtml(sale.customer_name)}<br/>Pago: ${escapeHtml(sale.payment_method)}</p>
    <hr/>
    ${itemsHtml}
    <hr/>
    <div style="display:flex;justify-content:space-between;"><span>Subtotal</span><span>${formatMoney(sale.subtotal)}</span></div>
    <div style="display:flex;justify-content:space-between;"><span>IGV (18%)</span><span>${formatMoney(sale.igv)}</span></div>
    <div style="display:flex;justify-content:space-between;font-weight:700;font-size:1.05rem;margin-top:0.25rem;"><span>Total</span><span>${formatMoney(sale.total)}</span></div>
  `;
  $("#receipt-modal").showModal();
}

// Eventos
document.querySelectorAll("[data-demo-user]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("#username").value = btn.dataset.demoUser;
    $("#password").value = btn.dataset.demoPass;
  });
});

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").classList.add("hidden");
  try {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#username").value,
        password: $("#password").value,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Error de autenticación");
    }
    const data = await res.json();
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("pos_token", state.token);
    localStorage.setItem("pos_user", JSON.stringify(state.user));
    await initApp();
  } catch (err) {
    $("#login-error").textContent = err.message;
    $("#login-error").classList.remove("hidden");
  }
});

$("#logout-btn").addEventListener("click", logout);

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    tab.classList.add("active");
    $(`#tab-${tab.dataset.tab}`).classList.remove("hidden");
  });
});

$("#pos-search").addEventListener("input", refreshProducts);
$("#filter-low-stock").addEventListener("change", refreshProducts);

$("#checkout-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.cart.size) {
    showToast("El carrito está vacío.");
    return;
  }
  const items = Array.from(state.cart.values()).map(({ product, quantity }) => ({
    product_id: product.id,
    quantity,
  }));
  try {
    const res = await apiFetch("/api/v1/sales", {
      method: "POST",
      body: JSON.stringify({
        customer_name: $("#customer-name").value,
        payment_method: $("#payment-method").value,
        items,
      }),
    });
    const sale = await res.json();
    state.cart.clear();
    renderCart();
    showReceipt(sale);
    await Promise.all([refreshDashboard(), refreshProducts(), refreshSales()]);
  } catch (err) {
    showToast(err.message);
  }
});

$("#new-product-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await apiFetch("/api/v1/products", {
      method: "POST",
      body: JSON.stringify({
        sku: $("#p-sku").value,
        name: $("#p-name").value,
        category: $("#p-category").value,
        unit_price: $("#p-price").value,
        stock: Number($("#p-stock").value),
        min_stock: Number($("#p-min").value),
        expires_at: $("#p-expiry").value || null,
      }),
    });
    e.target.reset();
    showToast("Producto creado correctamente.");
    await Promise.all([refreshProducts(), refreshDashboard()]);
  } catch (err) {
    showToast(err.message);
  }
});

$("#open-cash-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await apiFetch("/api/v1/cash/open", {
      method: "POST",
      body: JSON.stringify({ opening_amount: $("#opening-amount").value }),
    });
    $("#cash-close-summary").classList.add("hidden");
    showToast("Turno de caja abierto.");
    await Promise.all([refreshCash(), refreshDashboard()]);
  } catch (err) {
    showToast(err.message);
  }
});

$("#close-cash-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const res = await apiFetch("/api/v1/cash/close", {
      method: "POST",
      body: JSON.stringify({ closing_amount: $("#closing-amount").value }),
    });
    const closed = await res.json();
    const box = $("#cash-close-summary");
    box.classList.remove("hidden");
    box.innerHTML = `<strong>Resumen de cierre:</strong> Esperado ${formatMoney(closed.expected_amount)} · Contado ${formatMoney(closed.closing_amount)} · Diferencia: <strong>${formatMoney(closed.difference)}</strong>`;
    e.target.reset();
    showToast("Caja cerrada y cuadrada.");
    await Promise.all([refreshCash(), refreshDashboard()]);
  } catch (err) {
    showToast(err.message);
  }
});

$("#download-csv-btn").addEventListener("click", async () => {
  try {
    const res = await apiFetch("/api/v1/reports/sales.csv");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "reporte_ventas.csv";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast(err.message);
  }
});

$("#close-receipt-btn").addEventListener("click", () => $("#receipt-modal").close());

renderCart();
initApp();
