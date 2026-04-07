const loginForm = document.getElementById("loginForm");
const authMessage = document.getElementById("authMessage");
const registerForm = document.getElementById("registerForm");
const registerMessage = document.getElementById("registerMessage");

bootstrap();

async function bootstrap() {
  try {
    const session = await apiRequest("/api/session");
    if (session.authenticated) {
      window.location.href = session.role === "admin" ? "/admin.html" : "/user.html";
    }
  } catch (error) {
    authMessage.textContent = "";
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.textContent = "Checking credentials...";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const role = document.getElementById("role").value;

  try {
    const payload = await apiRequest("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    });

    window.location.href = payload.role === "admin" ? "/admin.html" : "/user.html";
  } catch (error) {
    authMessage.textContent = error.message;
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerMessage.textContent = "Creating account...";

  const username = document.getElementById("registerUsername").value.trim();
  const password = document.getElementById("registerPassword").value.trim();

  try {
    await apiRequest("/api/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });

    registerMessage.textContent = "Account created. You can now sign in as a user.";
    registerForm.reset();
  } catch (error) {
    registerMessage.textContent = error.message;
  }
});
