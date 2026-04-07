let adminData = null;
let refreshTimer = null;

const logoutButton = document.getElementById("logoutBtn");
const seedButton = document.getElementById("seedBtn");
const resetButton = document.getElementById("resetBtn");
const menuToggleButton = document.getElementById("menuToggleBtn");
const topbarNav = document.getElementById("topbarNav");
const deleteUserForm = document.getElementById("deleteUserForm");
const deleteUserMessage = document.getElementById("deleteUserMessage");

if (logoutButton) {
  logoutButton.addEventListener("click", logout);
}

if (seedButton) {
  seedButton.addEventListener("click", async () => {
    await apiRequest("/api/admin/seed", { method: "POST" });
    await loadAdmin();
  });
}

if (resetButton) {
  resetButton.addEventListener("click", async () => {
    await apiRequest("/api/admin/reset", { method: "POST" });
    await loadAdmin();
  });
}

if (deleteUserForm) {
  deleteUserForm.addEventListener("submit", handleDeleteUser);
}

if (menuToggleButton && topbarNav) {
  menuToggleButton.addEventListener("click", () => {
    const isOpen = topbarNav.classList.toggle("is-open");
    menuToggleButton.setAttribute("aria-expanded", String(isOpen));
  });
}

bootstrap();

async function bootstrap() {
  try {
    const session = await apiRequest("/api/session");
    if (!session.authenticated || session.role !== "admin") {
      window.location.href = "/index.html";
      return;
    }

    renderLiveHeader();
    await loadAdmin();
    startAutoRefresh();
  } catch (error) {
    window.location.href = "/index.html";
  }
}

async function loadAdmin() {
  adminData = await apiRequest("/api/admin/dashboard");
  renderLiveHeader();
  renderSummary();
  renderWeekGrid();
  renderAdminTable();
}

function renderSummary() {
  setText("adminHabitCount", String(adminData.total_habits));
  setText("adminCompletionCount", String(adminData.total_completions));
  setText("adminActiveToday", String(adminData.completed_today));
  setText("adminUserCount", String(adminData.user_count));
  setText("adminCompletionRate", `${adminData.completion_rate}%`);
  setText("quickUsers", String(adminData.user_count));
}

function renderWeekGrid() {
  const host = document.getElementById("adminWeekGrid");
  if (!host) {
    return;
  }

  host.innerHTML = adminData.week
    .map(
      (day) => `
        <article class="day-card">
          <span class="meta-text">${day.label}</span>
          <strong>${day.completed}</strong>
          <span class="meta-text">total checks</span>
        </article>
      `
    )
    .join("");
}

function renderAdminTable() {
  const tableHost = document.getElementById("adminHabitTable");
  if (!tableHost) {
    return;
  }

  if (!adminData.habits.length) {
    tableHost.innerHTML = '<div class="empty-state">No habits are currently stored.</div>';
    return;
  }

  const rows = buildAdminTableRows(adminData.habits);
  tableHost.innerHTML = `
    <div class="sheet-wrap">
      <table class="sheet-table">
        <thead>
          <tr>
            <th>User</th>
            <th>Habit</th>
            <th>Category</th>
            <th>Goal</th>
            <th>Created</th>
            <th>Current streak</th>
            <th>Best streak</th>
            <th>Total completions</th>
            <th>Completed dates</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

async function logout() {
  stopAutoRefresh();
  await apiRequest("/api/logout", { method: "POST" });
  window.location.href = "/index.html";
}

async function handleDeleteUser(event) {
  event.preventDefault();

  const usernameInput = document.getElementById("deleteUsername");
  const username = usernameInput.value.trim();
  if (!username) {
    setMessage("Enter a username to delete.");
    return;
  }

  setMessage(`Deleting ${username}...`);

  try {
    await apiRequest("/api/admin/delete_user", {
      method: "POST",
      body: JSON.stringify({ username }),
    });
    usernameInput.value = "";
    setMessage(`Deleted user ${username}.`);
    await loadAdmin();
  } catch (error) {
    setMessage(error.message);
  }
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function setMessage(value) {
  if (deleteUserMessage) {
    deleteUserMessage.textContent = value;
  }
}

function renderLiveHeader() {
  const now = new Date();
  setText(
    "pageDate",
    now.toLocaleDateString("en-IN", {
      weekday: "short",
      day: "2-digit",
      month: "short",
    })
  );
}

function startAutoRefresh() {
  stopAutoRefresh();
  refreshTimer = window.setInterval(async () => {
    try {
      await loadAdmin();
    } catch (error) {
      stopAutoRefresh();
    }
  }, 60000);
}

function stopAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function buildAdminTableRows(habits) {
  const grouped = new Map();

  habits.forEach((habit) => {
    if (!grouped.has(habit.owner)) {
      grouped.set(habit.owner, []);
    }
    grouped.get(habit.owner).push(habit);
  });

  return Array.from(grouped.entries())
    .map(([owner, ownerHabits]) =>
      ownerHabits
        .map(
          (habit, index) => `
            <tr>
              ${
                index === 0
                  ? `<td class="sheet-user" rowspan="${ownerHabits.length}">${escapeHtml(owner)}</td>`
                  : ""
              }
              <td>${escapeHtml(habit.name)}</td>
              <td>${escapeHtml(habit.category)}</td>
              <td class="sheet-notes">${escapeHtml(habit.goal)}</td>
              <td>${formatDate(habit.created_at)}</td>
              <td>${habit.current_streak}</td>
              <td>${habit.best_streak}</td>
              <td>${habit.total_completions}</td>
              <td class="sheet-notes">${habit.completed_dates.length ? habit.completed_dates.map(escapeHtml).join(", ") : "-"}</td>
            </tr>
          `
        )
        .join("")
    )
    .join("");
}
