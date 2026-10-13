const API = window.BIZPILOT_API || "https://bizpilot-ai-api.onrender.com";
const $ = (id) => document.getElementById(id);
const page = location.pathname.split("/").pop();

let token = sessionStorage.getItem("bp_token") || localStorage.getItem("bp_token") || "";
let currentUser = null;
let customersCache = [];
let invoicesCache = [];
let tasksCache = [];
let taskFilter = "All";
let usersCache = [];
let toastTimer;

function showMessage(text, isError = true) {
  const node = $("loginMessage");

  if (node) {
    node.textContent = text;
    node.style.color = isError ? "#b34444" : "#158252";
  } else {
    showToast(text);
  }
}

function showToast(text) {
  const node = $("toast");

  if (!node) return;

  node.textContent = text;
  node.classList.add("show");

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    node.classList.remove("show");
  }, 3200);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API}${path}`, {
    ...options,
    headers
  });

  const data = response.status === 204
    ? null
    : await response.json().catch(() => ({}));

  if (!response.ok) {
    if (response.status === 401 && page === "dashboard.html") {
      logout();
    }

    throw new Error(data?.detail || `Request failed (${response.status})`);
  }

  return data;
}

// LOGIN

function saveSession(data, remember) {
  token = data.access_token;
  currentUser = data.user;

  sessionStorage.removeItem("bp_token");
  localStorage.removeItem("bp_token");

  (remember ? localStorage : sessionStorage).setItem("bp_token", token);
}

function logout(redirect = true) {
  token = "";
  currentUser = null;

  sessionStorage.removeItem("bp_token");
  localStorage.removeItem("bp_token");

  if (redirect) {
    location.href = "index.html";
  }
}

async function login(email, password, remember) {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email,
      password
    })
  });

  saveSession(data, remember);

  location.href = "dashboard.html";
}

$("loginForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const button = event.currentTarget.querySelector('button[type="submit"]');

  if (button) {
    button.disabled = true;
    button.textContent = "Signing in...";
  }

  try {
    await login(
      $("email").value.trim(),
      $("password").value,
      $("remember")?.checked
    );
  } catch (error) {
    showMessage(error.message);

    if (button) {
      button.disabled = false;
      button.innerHTML = 'Sign in <span>→</span>';
    }
  }
});

$("togglePassword")?.addEventListener("click", () => {
  const input = $("password");

  if (!input) return;

  input.type = input.type === "password" ? "text" : "password";

  $("togglePassword").textContent =
    input.type === "password" ? "Show" : "Hide";
});

// GOOGLE LOGIN

window.handleGoogleCredential = async (response) => {
  try {
    const data = await api("/auth/google", {
      method: "POST",
      body: JSON.stringify({
        credential: response.credential
      })
    });

    saveSession(data, $("remember")?.checked);

    location.href = "dashboard.html";
  } catch (error) {
    showMessage(error.message);
  }
};

async function initGoogle() {
  try {
    const response = await fetch(`${API}/auth/google-config`);
    const data = await response.json();

    if (data.client_id && window.google?.accounts?.id) {
      $("g_id_onload")?.setAttribute("data-client_id", data.client_id);

      google.accounts.id.initialize({
        client_id: data.client_id,
        callback: window.handleGoogleCredential
      });

      const signIn = $("g_id_signin");

      if (signIn) {
        google.accounts.id.renderButton(signIn, {
          theme: "outline",
          size: "large",
          shape: "pill",
          text: "continue_with",
          width: 280
        });
      }
    }
  } catch (error) {
    console.error("Google login initialization failed:", error);
  }
}

if (page === "index.html" || page === "") {
  initGoogle();
}

// COMMON HELPERS

function money(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(Number(value || 0));
}

function dateText(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric"
  });
}

function safe(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[c]);
}

function setNotice(text) {
  const node = $("notice");

  if (node) {
    node.textContent = text;
    node.classList.add("show");
  }
}

function hideNotice() {
  $("notice")?.classList.remove("show");
}

// NAVIGATION

function switchView(name) {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.add("hidden");
  });

  $(`view-${name}`)?.classList.remove("hidden");

  document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });

  const titles = {
    overview: [
      "YOUR WORKSPACE",
      "Good to see you ✦",
      "Here is what's happening in your business today."
    ],
    customers: [
      "RELATIONSHIPS",
      "Customers",
      "Manage the people you do business with."
    ],
    invoices: [
      "FINANCE",
      "Invoices",
      "Keep track of billing and payment status."
    ],
    tasks: [
      "GET THINGS DONE",
      "Tasks",
      "Your next steps, organized."
    ],
    team: [
      "ADMINISTRATION",
      "Team & access",
      "Manage team accounts and permissions."
    ],
    assistant: [
      "BIZPILOT AI",
      "Smart Assistant ✦",
      "Get answers from BizPilot AI."
    ]
  };

  const title = titles[name] || titles.overview;

  if ($("pageEyebrow")) {
    $("pageEyebrow").textContent = title[0];
  }

  if ($("pageTitle")) {
    $("pageTitle").textContent = title[1];
  }

  if ($("pageSubtitle")) {
    $("pageSubtitle").textContent = title[2];
  }

  $("sidebar")?.classList.remove("open");

  if (name === "customers") {
    loadCustomers().catch((error) => showToast(error.message));
  }

  if (name === "invoices") {
    loadInvoices().catch((error) => showToast(error.message));
  }

  if (name === "tasks") {
    loadTasks().catch((error) => showToast(error.message));
  }

  if (name === "team" && currentUser?.role === "admin") {
    loadTeam().catch((error) => showToast(error.message));
  }
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.view === "assistant") {
      location.href = "lumora.html";
      return;
    }
    switchView(button.dataset.view);
  });
});

$("menuButton")?.addEventListener("click", () => {
  $("sidebar")?.classList.toggle("open");
});

$("logoutButton")?.addEventListener("click", () => logout());

$("profileLogout")?.addEventListener("click", () => logout());

// CUSTOMERS

async function loadCustomers() {
  customersCache = await api("/customers");

  if ($("customersTable")) {
    $("customersTable").innerHTML = customersCache.length
      ? customersCache.map((customer) => `
        <tr>
          <td><b>${safe(customer.name)}</b></td>
          <td>${safe(customer.email)}</td>
          <td>${dateText(customer.created_at)}</td>
          <td>
            <button
              type="button"
              class="table-action"
              data-delete-customer="${customer.id}">
              Delete
            </button>
          </td>
        </tr>
      `).join("")
      : '<tr><td colspan="4" class="muted">No customers yet. Add your first customer.</td></tr>';
  }

  if ($("invoiceCustomer")) {
    $("invoiceCustomer").innerHTML =
      '<option value="">Choose customer</option>' +
      customersCache.map((customer) => `
        <option value="${customer.id}">
          ${safe(customer.name)} · ${safe(customer.email)}
        </option>
      `).join("");
  }
}

// INVOICES

async function loadInvoices() {
  invoicesCache = await api("/invoices");

  if (!$("invoicesTable")) return;

  $("invoicesTable").innerHTML = invoicesCache.length
    ? invoicesCache.map((invoice) => `
      <tr>
        <td>#${invoice.id}</td>

        <td>${safe(invoice.customer_name || "Customer")}</td>

        <td>${money(invoice.amount)}</td>

        <td>
          <span class="status-pill ${invoice.status === "Paid" ? "paid" : ""}">
            ${safe(invoice.status)}
          </span>
        </td>

        <td>
          <div class="invoice-actions">
            ${invoice.status === "Paid"
              ? "—"
              : `<button
                  type="button"
                  class="table-action"
                  data-pay-invoice="${invoice.id}">
                  Mark paid
                </button>`}

            <button
              type="button"
              class="table-action"
              data-edit-invoice="${invoice.id}">
              Edit
            </button>

            <button
              type="button"
              class="table-action"
              data-delete-invoice="${invoice.id}">
              Delete
            </button>
          </div>
        </td>
      </tr>
    `).join("")
    : '<tr><td colspan="5" class="muted">No invoices yet. Create your first invoice.</td></tr>';
}

// EDIT INVOICE

async function editInvoice(invoiceId) {
  const invoice = invoicesCache.find(
    (item) => String(item.id) === String(invoiceId)
  );

  if (!invoice) {
    showToast("Invoice not found. Refresh and try again.");
    return;
  }

  if (!customersCache.length) {
    try {
      await loadCustomers();
    } catch (error) {
      showToast(error.message);
      return;
    }
  }

  const currentCustomer = customersCache.find(
    (customer) => String(customer.id) === String(invoice.customer_id)
  );

  const customerOptions = customersCache.map((customer) => {
    return `${customer.id}: ${customer.name} (${customer.email})`;
  }).join("\n");

  const customerInput = prompt(
    `Edit customer ID for Invoice #${invoice.id}.\n\nAvailable customers:\n${customerOptions}`,
    String(currentCustomer?.id ?? invoice.customer_id ?? "")
  );

  if (customerInput === null) return;

  const customerId = Number(customerInput.trim());

  if (!Number.isInteger(customerId) || customerId <= 0) {
    showToast("Please enter a valid customer ID.");
    return;
  }

  const selectedCustomer = customersCache.find(
    (customer) => Number(customer.id) === customerId
  );

  if (!selectedCustomer) {
    showToast("Customer ID not found. Choose an existing customer.");
    return;
  }

  const amountInput = prompt(
    `Enter the new amount for Invoice #${invoice.id}:`,
    String(invoice.amount)
  );

  if (amountInput === null) return;

  const amount = Number(amountInput.trim());

  if (!Number.isFinite(amount) || amount <= 0) {
    showToast("Invoice amount must be greater than zero.");
    return;
  }

  if (!confirm(
    `Update Invoice #${invoice.id}?\n\n` +
    `Customer: ${selectedCustomer.name}\n` +
    `Amount: ${money(amount)}`
  )) {
    return;
  }

  try {
    await api(`/invoices/${invoice.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        customer_id: customerId,
        amount
      })
    });

    await Promise.all([
      loadInvoices(),
      loadDashboard()
    ]);

    showToast("Invoice updated successfully.");
  } catch (error) {
    showToast(error.message);
  }
}

// DELETE INVOICE

async function deleteInvoice(invoiceId) {
  const invoice = invoicesCache.find(
    (item) => String(item.id) === String(invoiceId)
  );

  if (!invoice) {
    showToast("Invoice not found. Refresh and try again.");
    return;
  }

  const confirmed = confirm(
    `Are you sure you want to delete Invoice #${invoice.id}?\n\n` +
    `Customer: ${invoice.customer_name || "Customer"}\n` +
    `Amount: ${money(invoice.amount)}\n\n` +
    "This action cannot be undone."
  );

  if (!confirmed) return;

  try {
    await api(`/invoices/${invoice.id}`, {
      method: "DELETE"
    });

    await Promise.all([
      loadInvoices(),
      loadDashboard()
    ]);

    showToast(`Invoice #${invoice.id} deleted successfully.`);
  } catch (error) {
    showToast(error.message);
  }
}

// TASKS

async function loadTasks() {
  tasksCache = await api("/tasks");
  renderTasks();
}

function renderTasks() {
  const list = $("tasksList");

  if (!list) return;

  const statuses = ["All", "Pending", "In Progress", "Completed"];

  const filteredTasks = taskFilter === "All"
    ? tasksCache
    : tasksCache.filter((task) => task.status === taskFilter);

  list.innerHTML = `
    <div class="task-filters">
      ${statuses.map((status) => {
        const count = status === "All"
          ? tasksCache.length
          : tasksCache.filter((task) => task.status === status).length;

        return `
          <button
            type="button"
            class="table-action"
            data-task-filter="${status}"
            aria-pressed="${taskFilter === status ? "true" : "false"}">
            ${status} (${count})
          </button>
        `;
      }).join("")}
    </div>

    ${filteredTasks.length
      ? filteredTasks.map((task) => `
        <div class="task-row">
          <div class="task-main">
            <b>${safe(task.title)}</b>

            <small>
              ${safe(task.priority)} priority ·
              ${task.assigned_to ? "Assigned to team member" : "Shared task"}
            </small>

            ${task.description
              ? `<p>${safe(task.description)}</p>`
              : ""}
          </div>

          <select
            aria-label="Task status"
            data-task-status="${task.id}">
            ${statuses.slice(1).map((status) => `
              <option
                value="${status}"
                ${task.status === status ? "selected" : ""}>
                ${status}
              </option>
            `).join("")}
          </select>

          <div class="task-actions">
            <button
              type="button"
              class="table-action"
              data-edit-task="${task.id}">
              Edit
            </button>

            <button
              type="button"
              class="table-action"
              data-delete-task="${task.id}">
              Delete
            </button>
          </div>
        </div>
      `).join("")
      : `<p class="muted">${taskFilter === "All"
        ? "No tasks yet. Add a task to get started."
        : "No tasks in this status."}</p>`}
  `;
}

// TEAM

async function loadTeam() {
  const [overview, users] = await Promise.all([
    api("/admin/overview"),
    api("/admin/users")
  ]);

  usersCache = users;

  if ($("teamCount")) {
    $("teamCount").textContent = overview.users;
  }

  if ($("adminCustomers")) {
    $("adminCustomers").textContent = overview.customers;
  }

  if ($("adminInvoices")) {
    $("adminInvoices").textContent = overview.invoices;
  }

  if ($("adminTasks")) {
    $("adminTasks").textContent = overview.tasks;
  }

  if (!$("usersTable")) return;

  $("usersTable").innerHTML = users.map((user) => `
    <tr>
      <td><b>${safe(user.name)}</b></td>

      <td>${safe(user.email)}</td>

      <td>
        <span class="status-pill ${user.role === "admin" ? "completed" : ""}">
          ${safe(user.role)}
        </span>
      </td>

      <td>
        <span class="status-pill ${user.is_active ? "active" : "inactive"}">
          ${user.is_active ? "Active" : "Inactive"}
        </span>
      </td>

      <td>
        ${user.id === currentUser?.id
          ? "You"
          : `<button
              type="button"
              class="table-action"
              data-user-status="${user.id}"
              data-active="${user.is_active}">
              ${user.is_active ? "Deactivate" : "Activate"}
            </button>`}
      </td>
    </tr>
  `).join("");
}

// DASHBOARD

async function loadDashboard() {
  const [data, customers, invoices, tasks] = await Promise.all([
    api("/dashboard"),
    api("/customers"),
    api("/invoices"),
    api("/tasks")
  ]);

  customersCache = customers;
  invoicesCache = invoices;
  tasksCache = tasks;

  if ($("customerCount")) {
    $("customerCount").textContent = data.customer_count;
  }

  if ($("invoiceCount")) {
    $("invoiceCount").textContent = data.invoice_count;
  }

  if ($("totalInvoiced")) {
    $("totalInvoiced").textContent = money(data.total_invoiced);
  }

  if ($("pendingTotal")) {
    $("pendingTotal").textContent = money(data.pending_total);
  }

  if ($("paidTotal")) {
    $("paidTotal").textContent = money(data.paid_total);
  }

  if ($("pendingLegend")) {
    $("pendingLegend").textContent = money(data.pending_total);
  }

  const percent = data.total_invoiced
    ? Math.round(data.paid_total / data.total_invoiced * 100)
    : 0;

  if ($("paidPercent")) {
    $("paidPercent").textContent = `${percent}%`;
  }

  if ($("paymentRing")) {
    $("paymentRing").style.setProperty("--paid", `${percent}%`);
  }

  const activity = [
    ...invoices.slice(0, 3).map((invoice) => ({
      icon: "▤",
      title: `Invoice #${invoice.id} · ${invoice.customer_name || "Customer"}`,
      detail: `${invoice.status} · ${dateText(invoice.created_at)}`,
      amount: money(invoice.amount)
    })),

    ...customers.slice(0, 3).map((customer) => ({
      icon: "♧",
      title: customer.name,
      detail: `Customer added · ${dateText(customer.created_at)}`,
      amount: ""
    })),

    ...tasks.slice(0, 2).map((task) => ({
      icon: "☑",
      title: task.title,
      detail: `Task · ${task.status}`,
      amount: ""
    }))
  ].slice(0, 6);

  if ($("activityList")) {
    $("activityList").innerHTML = activity.length
      ? activity.map((item) => `
        <div class="activity-row">
          <div class="activity-icon">${item.icon}</div>

          <div>
            <b>${safe(item.title)}</b>
            <small>${safe(item.detail)}</small>
          </div>

          <strong>${safe(item.amount)}</strong>
        </div>
      `).join("")
      : '<p class="muted">Your latest activity will appear here.</p>';
  }
}

// QUICK ACTIONS

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const kind = button.dataset.action;

    const forms = {
      customer: "customerForm",
      invoice: "invoiceForm",
      task: "taskForm"
    };

    const formId = forms[kind];

    if (!formId || !$(formId)) return;

    if (kind === "invoice" && !customersCache.length) {
      loadCustomers().catch((error) => showToast(error.message));
    }

    if (page === "dashboard.html") {
      switchView(
        kind === "customer"
          ? "customers"
          : kind === "invoice"
            ? "invoices"
            : "tasks"
      );
    }

    $(formId).classList.remove("hidden");

    if (kind === "customer") $("customerName")?.focus();
    if (kind === "invoice") $("invoiceCustomer")?.focus();
    if (kind === "task") $("taskTitle")?.focus();
  });
});

document.querySelectorAll("[data-cancel]").forEach((button) => {
  button.addEventListener("click", () => {
    $(`${button.dataset.cancel}Form`)?.classList.add("hidden");
  });
});

// CREATE CUSTOMER

$("customerForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    await api("/customers", {
      method: "POST",
      body: JSON.stringify({
        name: $("customerName").value.trim(),
        email: $("customerEmail").value.trim()
      })
    });

    event.target.reset();
    event.target.classList.add("hidden");

    await Promise.all([
      loadCustomers(),
      loadDashboard()
    ]);

    showToast("Customer saved.");
  } catch (error) {
    showToast(error.message);
  }
});

// CREATE INVOICE

$("invoiceForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    await api("/invoices", {
      method: "POST",
      body: JSON.stringify({
        customer_id: Number($("invoiceCustomer").value),
        amount: Number($("invoiceAmount").value)
      })
    });

    event.target.reset();
    event.target.classList.add("hidden");

    await Promise.all([
      loadInvoices(),
      loadDashboard()
    ]);

    showToast("Invoice created.");
  } catch (error) {
    showToast(error.message);
  }
});

// CREATE TASK

$("taskForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    await api("/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: $("taskTitle").value.trim(),
        priority: $("taskPriority").value
      })
    });

    event.target.reset();
    event.target.classList.add("hidden");

    await Promise.all([
      loadTasks(),
      loadDashboard()
    ]);

    showToast("Task created.");
  } catch (error) {
    showToast(error.message);
  }
});

// CREATE TEAM USER

$("userForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    await api("/admin/users", {
      method: "POST",
      body: JSON.stringify({
        name: $("newUserName").value.trim(),
        email: $("newUserEmail").value.trim(),
        password: $("newUserPassword").value,
        role: $("newUserRole").value
      })
    });

    event.target.reset();

    await loadTeam();

    showToast("Account created. Share the temporary password securely.");
  } catch (error) {
    showToast(error.message);
  }
});

// TASK EDIT, TASK DELETE, INVOICE ACTIONS, AND OTHER ACTIONS

document.addEventListener("click", async (event) => {
  const filterButton = event.target.closest("[data-task-filter]");

  if (filterButton) {
    taskFilter = filterButton.dataset.taskFilter;
    renderTasks();
    return;
  }

  // EDIT TASK

  const editTaskButton = event.target.closest("[data-edit-task]");

  if (editTaskButton) {
    const task = tasksCache.find(
      (item) => String(item.id) === editTaskButton.dataset.editTask
    );

    if (!task) {
      showToast("Task not found. Refresh and try again.");
      return;
    }

    const title = prompt("Enter task title:", task.title);

    if (title === null) return;

    if (!title.trim()) {
      showToast("Task title cannot be empty.");
      return;
    }

    const description = prompt(
      "Enter task description:",
      task.description || ""
    );

    if (description === null) return;

    const priority = prompt(
      "Enter priority (Low, Medium, High):",
      task.priority || "Medium"
    );

    if (priority === null) return;

    const normalizedPriority = priority.trim();

    if (!["Low", "Medium", "High"].includes(normalizedPriority)) {
      showToast("Priority must be Low, Medium, or High.");
      return;
    }

    try {
      await api(`/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          priority: normalizedPriority
        })
      });

      await Promise.all([
        loadTasks(),
        loadDashboard()
      ]);

      showToast("Task updated successfully.");
    } catch (error) {
      showToast(error.message);
    }

    return;
  }

  // DELETE TASK

  const deleteTaskButton = event.target.closest("[data-delete-task]");

  if (deleteTaskButton) {
    const taskId = deleteTaskButton.dataset.deleteTask;

    if (!confirm("Are you sure you want to delete this task?")) {
      return;
    }

    try {
      await api(`/tasks/${taskId}`, {
        method: "DELETE"
      });

      await Promise.all([
        loadTasks(),
        loadDashboard()
      ]);

      showToast("Task deleted successfully.");
    } catch (error) {
      showToast(error.message);
    }

    return;
  }

  // EDIT INVOICE

  const editInvoiceButton = event.target.closest("[data-edit-invoice]");

  if (editInvoiceButton) {
    await editInvoice(editInvoiceButton.dataset.editInvoice);
    return;
  }

  // DELETE INVOICE

  const deleteInvoiceButton = event.target.closest("[data-delete-invoice]");

  if (deleteInvoiceButton) {
    await deleteInvoice(deleteInvoiceButton.dataset.deleteInvoice);
    return;
  }

  // DELETE CUSTOMER

  const deleteCustomerButton = event.target.closest("[data-delete-customer]");

  if (deleteCustomerButton && confirm("Delete this customer?")) {
    try {
      await api(
        `/customers/${deleteCustomerButton.dataset.deleteCustomer}`,
        {
          method: "DELETE"
        }
      );

      await Promise.all([
        loadCustomers(),
        loadDashboard()
      ]);

      showToast("Customer deleted.");
    } catch (error) {
      showToast(error.message);
    }

    return;
  }

  // MARK INVOICE AS PAID

  const payButton = event.target.closest("[data-pay-invoice]");

  if (payButton && confirm("Mark this invoice as paid?")) {
    try {
      await api(`/invoices/${payButton.dataset.payInvoice}/pay`, {
        method: "PATCH"
      });

      await Promise.all([
        loadInvoices(),
        loadDashboard()
      ]);

      showToast("Invoice marked paid.");
    } catch (error) {
      showToast(error.message);
    }

    return;
  }

  // ACTIVATE / DEACTIVATE TEAM USER

  const userButton = event.target.closest("[data-user-status]");

  if (userButton) {
    try {
      await api(`/admin/users/${userButton.dataset.userStatus}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          is_active: userButton.dataset.active !== "true"
        })
      });

      await loadTeam();

      showToast("User access updated.");
    } catch (error) {
      showToast(error.message);
    }
  }
});

// UPDATE TASK STATUS

document.addEventListener("change", async (event) => {
  const select = event.target.closest("[data-task-status]");

  if (!select) return;

  try {
    await api(`/tasks/${select.dataset.taskStatus}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: select.value
      })
    });

    await Promise.all([
      loadTasks(),
      loadDashboard()
    ]);

    showToast("Task status updated.");
  } catch (error) {
    showToast(error.message);
  }
});

// GLOBAL SEARCH

$("globalSearch")?.addEventListener("input", (event) => {
  const query = event.target.value.toLowerCase();

  document.querySelectorAll("tbody tr, .task-row, .activity-row").forEach((row) => {
    row.style.display = row.textContent.toLowerCase().includes(query)
      ? ""
      : "none";
  });
});

// INITIALIZE DASHBOARD

async function initDashboard() {
  if (!token) {
    location.href = "index.html";
    return;
  }

  try {
    currentUser = await api("/auth/me");

    if ($("profileName")) {
      $("profileName").textContent = currentUser.name;
    }

    if ($("profileRole")) {
      $("profileRole").textContent = currentUser.role;
    }

    if ($("avatar")) {
      $("avatar").textContent = (currentUser.name || "B")
        .trim()
        .charAt(0)
        .toUpperCase();
    }

    if (currentUser.role === "admin") {
      document.body.classList.add("is-admin");
    }

    if ($("dateLabel")) {
      $("dateLabel").textContent = new Date().toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
      });
    }

    await loadDashboard();

    if (currentUser.role === "admin") {
      loadTeam().catch(() => {});
    }
  } catch (error) {
    setNotice(error.message);
  }
}

if (page === "dashboard.html") {
  initDashboard();
}

/* =========================================
   GEMINI AI ASSISTANT + CHAT HISTORY
========================================= */

const chatForm = $("chatForm");
const chatInput = $("chatInput");
const chatMessages = $("chatMessages");
const chatSendButton = $("chatSendButton");

let currentConversationId = null;
let chatHistoryCache = [];
let chatRequestInProgress = false;

function scrollChatToBottom() {
  if (chatMessages) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

function clearChatMessages() {
  if (chatMessages) {
    chatMessages.replaceChildren();
  }
}

function addChatMessage(text, sender = "assistant", options = {}) {
  if (!chatMessages) return null;

  const wrapper = document.createElement("div");
  wrapper.className = `chat-message ${sender}`;

  const label = document.createElement("b");
  label.textContent = sender === "user" ? "You" : "BizPilot AI";

  const content = document.createElement("div");
  content.className = "chat-message-content";
  content.textContent = String(text);

  wrapper.append(label, content);

  if (sender === "assistant" && options.translate !== false) {
    const actions = document.createElement("div");
    actions.className = "chat-message-actions";

    const translateButton = document.createElement("button");
    translateButton.type = "button";
    translateButton.className = "table-action";
    translateButton.textContent = "🌐 Translate";

    translateButton.addEventListener("click", async () => {
      const language = prompt(
        "Translate this response into which language?",
        "Telugu"
      );

      if (!language || !language.trim()) return;

      translateButton.disabled = true;
      translateButton.textContent = "Translating...";

      try {
        const result = await api("/chat/translate", {
          method: "POST",
          body: JSON.stringify({
            text: content.textContent,
            target_language: language.trim()
          })
        });

        content.textContent = result.translated_text;

        translateButton.textContent =
          `Translated to ${result.target_language}`;
      } catch (error) {
        showToast(error.message);

        translateButton.disabled = false;
        translateButton.textContent = "🌐 Translate";
      }
    });

    actions.appendChild(translateButton);
    wrapper.appendChild(actions);
  }

  chatMessages.appendChild(wrapper);

  scrollChatToBottom();

  return wrapper;
}

function showChatWelcome() {
  clearChatMessages();

  const welcome = document.createElement("p");
  welcome.className = "muted";

  welcome.textContent =
    "Hi! I'm BizPilot AI. Ask me about your business or any other topic.";

  chatMessages?.appendChild(welcome);
}

function showChatLoading() {
  const loading = document.createElement("p");

  loading.className = "chat-loading";
  loading.textContent = "BizPilot AI is thinking...";

  chatMessages?.appendChild(loading);

  scrollChatToBottom();

  return loading;
}

/* =========================================
   CHAT HISTORY SIDEBAR
========================================= */

function renderChatHistory() {
  const historyContainer = $("chatHistory");

  if (!historyContainer) return;

  historyContainer.replaceChildren();

  if (!chatHistoryCache.length) {
    const empty = document.createElement("p");

    empty.className = "muted";
    empty.textContent = "No previous conversations.";

    historyContainer.appendChild(empty);

    return;
  }

  chatHistoryCache.forEach((conversation) => {
    const row = document.createElement("div");

    row.className = "chat-history-item";

    if (conversation.id === currentConversationId) {
      row.classList.add("active");
    }

    const openButton = document.createElement("button");

    openButton.type = "button";
    openButton.className = "chat-history-open";
    openButton.textContent = conversation.title || "New Chat";
    openButton.title = conversation.title || "New Chat";

    openButton.addEventListener("click", () => {
      openConversation(conversation.id).catch((error) => {
        showToast(error.message);
      });
    });

    const deleteButton = document.createElement("button");

    deleteButton.type = "button";
    deleteButton.className = "chat-history-delete";
    deleteButton.textContent = "×";
    deleteButton.title = "Delete conversation";

    deleteButton.setAttribute(
      "aria-label",
      "Delete conversation"
    );

    deleteButton.addEventListener("click", async () => {
      if (!confirm("Delete this conversation permanently?")) {
        return;
      }

      try {
        await api(`/chat/conversations/${conversation.id}`, {
          method: "DELETE"
        });

        if (currentConversationId === conversation.id) {
          currentConversationId = null;
          showChatWelcome();
        }

        await loadChatHistory();

        showToast("Conversation deleted.");
      } catch (error) {
        showToast(error.message);
      }
    });

    row.append(openButton, deleteButton);

    historyContainer.appendChild(row);
  });
}

async function loadChatHistory() {
  const historyContainer = $("chatHistory");

  if (!historyContainer) return;

  try {
    chatHistoryCache = await api("/chat/conversations");

    renderChatHistory();
  } catch (error) {
    console.error("Could not load chat history:", error);

    showToast(`Chat history: ${error.message}`);
  }
}

async function openConversation(conversationId) {
  if (chatRequestInProgress) {
    showToast("Please wait for the current response.");
    return;
  }

  const result = await api(
    `/chat/conversations/${conversationId}`
  );

  currentConversationId = result.conversation.id;

  clearChatMessages();

  if (!result.messages.length) {
    showChatWelcome();
  } else {
    result.messages.forEach((message) => {
      addChatMessage(
        message.content,
        message.role === "user" ? "user" : "assistant"
      );
    });
  }

  renderChatHistory();
}

/* =========================================
   CREATE NEW CHAT
========================================= */

async function startNewChat() {
  if (chatRequestInProgress) {
    showToast("Please wait for the current response.");
    return;
  }

  try {
    const conversation = await api("/chat/conversations", {
      method: "POST",
      body: JSON.stringify({
        title: "New Chat"
      })
    });

    currentConversationId = conversation.id;

    showChatWelcome();

    renderChatHistory();

    await loadChatHistory();

    chatInput?.focus();
  } catch (error) {
    showToast(error.message);
  }
}

$("newChatButton")?.addEventListener("click", () => {
  startNewChat();
});

/* =========================================
   SEND CHAT MESSAGE
========================================= */

if (chatForm && chatInput && chatMessages) {
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (chatRequestInProgress) return;

    const message = chatInput.value.trim();

    if (!message) return;

    chatRequestInProgress = true;

    addChatMessage(message, "user");

    chatInput.value = "";
    chatInput.disabled = true;

    if (chatSendButton) {
      chatSendButton.disabled = true;
      chatSendButton.textContent = "Thinking...";
    }

    const loading = showChatLoading();

    try {
      const payload = {
        message
      };

      if (currentConversationId !== null) {
        payload.conversation_id = currentConversationId;
      }

      const result = await api("/chat/", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      loading?.remove();

      if (result.conversation_id) {
        currentConversationId = result.conversation_id;
      }

      addChatMessage(
        result.reply || "No answer was returned.",
        "assistant"
      );

      await loadChatHistory();
    } catch (error) {
      loading?.remove();

      addChatMessage(
        `Sorry, something went wrong: ${error.message}`,
        "assistant",
        {
          translate: false
        }
      );

      console.error("BizPilot AI error:", error);
    } finally {
      chatRequestInProgress = false;

      chatInput.disabled = false;

      if (chatSendButton) {
        chatSendButton.disabled = false;
        chatSendButton.textContent = "Send";
      }

      chatInput.focus();
    }
  });
}

/* =========================================
   LOAD HISTORY WHEN OPENING ASSISTANT
========================================= */

const originalSwitchView = switchView;

switchView = function (name) {
  originalSwitchView(name);

  if (name === "assistant") {
    loadChatHistory().catch((error) => {
      console.error("Chat history loading failed:", error);
    });
  }
};