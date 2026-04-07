let userSession = null;
let userData = null;
let refreshTimer = null;

const logoutButton = document.getElementById("logoutBtn");
const habitForm = document.getElementById("habitForm");
const menuToggleButton = document.getElementById("menuToggleBtn");
const topbarNav = document.getElementById("topbarNav");

if (logoutButton) {
  logoutButton.addEventListener("click", logout);
}

if (habitForm) {
  habitForm.addEventListener("submit", addHabit);
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
    if (!session.authenticated || session.role !== "user") {
      window.location.href = "/index.html";
      return;
    }

    userSession = session;
    const identityHost = document.getElementById("sidebarIdentity");
    if (identityHost) {
      identityHost.textContent = session.username;
    }

    renderLiveHeader();
    await loadDashboard();
    startAutoRefresh();
  } catch (error) {
    window.location.href = "/index.html";
  }
}

async function loadDashboard() {
  userData = await apiRequest("/api/user/dashboard");
  renderLiveHeader();
  renderSummary();
  renderHabitList();
  renderWeekGrid();
  renderAnalysis();
  renderHistoryTable();
}

function renderSummary() {
  setText("completedToday", `${userData.completed_today} / ${userData.total_habits}`);
  setText("bestStreak", `${userData.best_streak} days`);
  setText("consistencyRate", `${userData.consistency_rate}%`);
  setText("habitCount", String(userData.total_habits));
  const completionRate = userData.total_habits
    ? Math.round((userData.completed_today / userData.total_habits) * 100)
    : 0;
  setText("quickCompletion", `${completionRate}%`);
}

function renderHabitList() {
  const list = document.getElementById("habitList");
  if (!list) {
    return;
  }

  if (!userData.habits.length) {
    list.innerHTML = '<div class="empty-state">No habits added yet. Create your first one above.</div>';
    return;
  }

  list.innerHTML = userData.habits
    .map(
      (habit) => `
        <article class="habit-item ${habit.done_today ? "is-complete" : ""}">
          <div class="habit-main">
            <div class="habit-head">
              <h3>${escapeHtml(habit.name)}</h3>
              <span class="tag">${escapeHtml(habit.category)}</span>
            </div>
            <p class="meta-text">Goal: ${escapeHtml(habit.goal)}</p>
            <p class="meta-text">
              Current streak: <strong>${habit.current_streak}</strong> |
              Best streak: <strong>${habit.best_streak}</strong> |
              Total completions: <strong>${habit.total_completions}</strong>
            </p>
          </div>
          <div class="habit-actions">
            <button class="primary-btn" type="button" data-action="toggle" data-id="${habit.id}">
              ${habit.done_today ? "Undo today" : "Mark done"}
            </button>
            <button class="secondary-btn" type="button" data-action="clear" data-id="${habit.id}">
              Mark missed
            </button>
            <button class="danger-btn" type="button" data-action="delete" data-id="${habit.id}">
              Delete
            </button>
          </div>
        </article>
      `
    )
    .join("");

  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const { action, id } = button.dataset;
      if (action === "toggle") {
        await apiRequest(`/api/habits/${id}/toggle`, { method: "POST" });
      } else if (action === "clear") {
        await apiRequest(`/api/habits/${id}/clear_today`, { method: "POST" });
      } else if (action === "delete") {
        await apiRequest(`/api/habits/${id}`, { method: "DELETE" });
      }

      await loadDashboard();
    });
  });
}

function renderWeekGrid() {
  const weekGrid = document.getElementById("weekGrid");
  if (!weekGrid) {
    return;
  }

  weekGrid.innerHTML = userData.week
    .map(
      (day) => `
        <article class="day-card">
          <span class="meta-text">${day.label}</span>
          <strong>${day.completed}</strong>
          <span class="meta-text">completed</span>
        </article>
      `
    )
    .join("");
}

function renderHistoryTable() {
  const historyTable = document.getElementById("historyTable");
  if (!historyTable) {
    return;
  }

  if (!userData.habits.length) {
    historyTable.innerHTML = '<div class="empty-state">No habit history available yet.</div>';
    return;
  }

  historyTable.innerHTML = `
    <div class="sheet-wrap">
      <table>
        <thead>
          <tr>
            <th>Habit</th>
            <th>Category</th>
            <th>Created</th>
            <th>Current streak</th>
            <th>Best streak</th>
            <th>Completed dates</th>
          </tr>
        </thead>
        <tbody>
          ${userData.habits
            .map(
              (habit) => `
                <tr>
                  <td>${escapeHtml(habit.name)}</td>
                  <td>${escapeHtml(habit.category)}</td>
                  <td>${formatDate(habit.created_at)}</td>
                  <td>${habit.current_streak}</td>
                  <td>${habit.best_streak}</td>
                  <td>${habit.completed_dates.length ? habit.completed_dates.map(escapeHtml).join(", ") : "-"}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAnalysis() {
  renderBarChart(
    document.getElementById("streakChart"),
    userData.habits,
    "current_streak",
    "days",
    "No streak data yet.",
    ""
  );
  renderBarChart(
    document.getElementById("completionChart"),
    userData.habits,
    "total_completions",
    "checks",
    "No completion data yet.",
    "coral-fill"
  );
}

function renderBarChart(host, habits, metricKey, metricLabel, emptyMessage, fillClass) {
  if (!host) {
    return;
  }

  if (!habits.length) {
    host.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
    return;
  }

  const maxValue = Math.max(...habits.map((habit) => habit[metricKey]), 1);
  host.innerHTML = habits
    .map((habit) => {
      const value = habit[metricKey];
      const width = Math.max((value / maxValue) * 100, value > 0 ? 8 : 0);
      return `
        <div class="bar-row">
          <div class="bar-meta">
            <span>${escapeHtml(habit.name)}</span>
            <strong>${value} ${metricLabel}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${fillClass}" style="width:${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

async function addHabit(event) {
  event.preventDefault();

  const nameInput = document.getElementById("habitName");
  const categoryInput = document.getElementById("habitCategory");
  const goalInput = document.getElementById("habitGoal");

  await apiRequest("/api/habits", {
    method: "POST",
    body: JSON.stringify({
      name: nameInput.value.trim(),
      category: categoryInput.value.trim(),
      goal: goalInput.value.trim(),
    }),
  });

  nameInput.value = "";
  categoryInput.value = "";
  goalInput.value = "";
  await loadDashboard();
}

async function logout() {
  stopAutoRefresh();
  await apiRequest("/api/logout", { method: "POST" });
  window.location.href = "/index.html";
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
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
      await loadDashboard();
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
