import json
import os
import secrets
import ssl
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from http import cookies
from urllib.parse import unquote, urlparse

import pg8000.dbapi


SESSION_COOKIE = "habitflow_session"
SESSION_LIFETIME_DAYS = 30


def admin_username():
    return os.environ.get("ADMIN_USERNAME", "abhi")


def admin_password():
    return os.environ.get("ADMIN_PASSWORD", "abhi")


def reserved_usernames():
    return {admin_username().lower(), "admin"}


def parse_database_url():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required.")

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL connection string.")

    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": unquote(parsed.path.lstrip("/")),
        "ssl_context": ssl.create_default_context(),
    }


def db_connection():
    return pg8000.dbapi.connect(**parse_database_url())


def initialize_database():
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS habits (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                goal TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS completions (
                id SERIAL PRIMARY KEY,
                habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                completed_on DATE NOT NULL,
                UNIQUE(habit_id, completed_on)
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                username TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL
            );
            """
        )
        connection.commit()


def now_utc():
    return datetime.now(timezone.utc)


def today_key():
    return now_utc().strftime("%Y-%m-%d")


def date_key(value):
    return value.strftime("%Y-%m-%d")


def starter_habits(user_id):
    timestamp = now_utc()
    return [
        (user_id, "Morning Walk", "Fitness", "20 minutes before 8 AM", timestamp),
        (user_id, "Read 20 Pages", "Learning", "Before going to bed", timestamp),
        (user_id, "Drink 2L Water", "Health", "Finish by 7 PM", timestamp),
    ]


def build_week_rows(habits):
    rows = []
    for offset in range(6, -1, -1):
        day_value = now_utc() - timedelta(days=offset)
        key = date_key(day_value)
        completed = sum(1 for habit in habits if key in habit["completed_dates"])
        rows.append({"label": day_value.strftime("%a"), "completed": completed})
    return rows


def current_streak(completed_dates):
    unique_dates = sorted(set(completed_dates), reverse=True)
    if not unique_dates:
        return 0

    cursor = now_utc()
    cursor_key = date_key(cursor)
    if cursor_key not in unique_dates:
        cursor -= timedelta(days=1)

    streak = 0
    while date_key(cursor) in unique_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def best_streak(completed_dates):
    unique_dates = sorted(set(completed_dates))
    if not unique_dates:
        return 0

    best = 1
    running = 1
    for index in range(1, len(unique_dates)):
        previous = datetime.fromisoformat(unique_dates[index - 1])
        current = datetime.fromisoformat(unique_dates[index])
        if (current - previous).days == 1:
            running += 1
            best = max(best, running)
        else:
            running = 1
    return best


def normalize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def rows_to_dicts(cursor):
    columns = [column[0] for column in cursor.description]
    return [
        {columns[index]: normalize_value(value) for index, value in enumerate(row)}
        for row in cursor.fetchall()
    ]


def row_to_dict(cursor):
    row = cursor.fetchone()
    if not row:
        return None
    columns = [column[0] for column in cursor.description]
    return {columns[index]: normalize_value(value) for index, value in enumerate(row)}


def seed_user_habits(connection, user_id):
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM completions WHERE habit_id IN (SELECT id FROM habits WHERE user_id = %s)",
        (user_id,),
    )
    cursor.execute("DELETE FROM habits WHERE user_id = %s", (user_id,))
    cursor.executemany(
        "INSERT INTO habits (user_id, name, category, goal, created_at) VALUES (%s, %s, %s, %s, %s)",
        starter_habits(user_id),
    )


def load_habits_for_user(connection, user_id):
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, name, category, goal, created_at
        FROM habits
        WHERE user_id = %s
        ORDER BY id DESC
        """,
        (user_id,),
    )
    habits = rows_to_dicts(cursor)

    cursor.execute(
        """
        SELECT c.habit_id, c.completed_on
        FROM completions c
        JOIN habits h ON h.id = c.habit_id
        WHERE h.user_id = %s
        ORDER BY c.completed_on ASC
        """,
        (user_id,),
    )
    completions = rows_to_dicts(cursor)

    completion_map = {}
    for row in completions:
        completion_map.setdefault(row["habit_id"], []).append(row["completed_on"])

    return [
        {
            **habit,
            "completed_dates": completion_map.get(habit["id"], []),
        }
        for habit in habits
    ]


def user_dashboard_payload(user_id):
    with db_connection() as connection:
        habits = load_habits_for_user(connection, user_id)

    today = today_key()
    shaped_habits = [
        {
            **habit,
            "done_today": today in habit["completed_dates"],
            "current_streak": current_streak(habit["completed_dates"]),
            "best_streak": best_streak(habit["completed_dates"]),
            "total_completions": len(habit["completed_dates"]),
        }
        for habit in habits
    ]

    total_habits = len(shaped_habits)
    completed_today = sum(1 for habit in shaped_habits if habit["done_today"])
    best_overall = max((habit["best_streak"] for habit in shaped_habits), default=0)
    week = build_week_rows(shaped_habits)
    possible = total_habits * 7
    consistency_rate = round((sum(day["completed"] for day in week) / possible) * 100) if possible else 0

    return {
        "total_habits": total_habits,
        "completed_today": completed_today,
        "best_streak": best_overall,
        "consistency_rate": consistency_rate,
        "week": week,
        "habits": shaped_habits,
    }


def admin_dashboard_payload():
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, username, created_at FROM users ORDER BY username ASC")
        users = rows_to_dicts(cursor)

        habits = []
        for user in users:
            for habit in load_habits_for_user(connection, user["id"]):
                habits.append(
                    {
                        **habit,
                        "owner": user["username"],
                        "current_streak": current_streak(habit["completed_dates"]),
                        "best_streak": best_streak(habit["completed_dates"]),
                        "total_completions": len(habit["completed_dates"]),
                    }
                )

    today = today_key()
    total_habits = len(habits)
    total_completions = sum(habit["total_completions"] for habit in habits)
    completed_today = sum(1 for habit in habits if today in habit["completed_dates"])
    week = build_week_rows(habits)
    possible = total_habits * 7
    completion_rate = round((sum(day["completed"] for day in week) / possible) * 100) if possible else 0

    return {
        "user_count": len(users),
        "total_habits": total_habits,
        "total_completions": total_completions,
        "completed_today": completed_today,
        "completion_rate": completion_rate,
        "week": week,
        "habits": habits,
    }


def parse_cookies(headers):
    raw = headers.get("Cookie")
    if not raw:
        return {}
    jar = cookies.SimpleCookie()
    jar.load(raw)
    return {key: morsel.value for key, morsel in jar.items()}


def should_set_secure_cookie(headers):
    forwarded_proto = headers.get("x-forwarded-proto") or headers.get("X-Forwarded-Proto")
    return forwarded_proto == "https" or os.environ.get("VERCEL") == "1"


def serialize_cookie(name, value, *, expires=None, http_only=True, secure=False):
    jar = cookies.SimpleCookie()
    jar[name] = value
    jar[name]["path"] = "/"
    jar[name]["samesite"] = "Lax"
    if http_only:
        jar[name]["httponly"] = True
    if secure:
        jar[name]["secure"] = True
    if expires:
        jar[name]["expires"] = expires
    return jar[name].OutputString()


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: list[tuple[str, str]] | None = None


class HabitFlowApp:
    def __init__(self):
        self._database_ready = False

    def ensure_database(self):
        if self._database_ready:
            return
        initialize_database()
        self._database_ready = True

    def json_response(self, payload, status=200, headers=None):
        return Response(
            status=status,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            headers=headers or [],
        )

    def current_session(self, headers):
        token = parse_cookies(headers).get(SESSION_COOKIE)
        if not token:
            return None

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT token, role, username, user_id, expires_at
                FROM sessions
                WHERE token = %s AND expires_at > %s
                """,
                (token, now_utc()),
            )
            session = row_to_dict(cursor)
            cursor.execute("DELETE FROM sessions WHERE expires_at <= %s", (now_utc(),))
            connection.commit()
        return session

    def read_json(self, body):
        raw = body.decode("utf-8") if body else "{}"
        return json.loads(raw or "{}")

    def create_session(self, session_data, headers):
        token = secrets.token_hex(24)
        expires_at = now_utc() + timedelta(days=SESSION_LIFETIME_DAYS)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (token, role, username, user_id, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    token,
                    session_data["role"],
                    session_data["username"],
                    session_data.get("user_id"),
                    expires_at,
                ),
            )
            connection.commit()

        cookie_value = serialize_cookie(
            SESSION_COOKIE,
            token,
            http_only=True,
            secure=should_set_secure_cookie(headers),
        )
        return cookie_value

    def clear_session(self, headers):
        token = parse_cookies(headers).get(SESSION_COOKIE)
        if token:
            with db_connection() as connection:
                cursor = connection.cursor()
                cursor.execute("DELETE FROM sessions WHERE token = %s", (token,))
                connection.commit()

        cookie_value = serialize_cookie(
            SESSION_COOKIE,
            "",
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
            http_only=True,
            secure=should_set_secure_cookie(headers),
        )
        return cookie_value

    def require_role(self, headers, role):
        session = self.current_session(headers)
        if not session or session["role"] != role:
            return None, self.json_response({"error": "Unauthorized."}, 401)
        return session, None

    def user_owns_habit(self, user_id, habit_id):
        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM habits WHERE id = %s AND user_id = %s",
                (habit_id, user_id),
            )
            habit = cursor.fetchone()
        return bool(habit)

    def extract_habit_id(self, path):
        parts = [part for part in path.split("/") if part]
        return int(parts[2])

    def handle_register(self, body):
        payload = self.read_json(body)
        username = payload.get("username", "").strip()
        password = payload.get("password", "").strip()

        if len(username) < 3 or len(password) < 3:
            return self.json_response({"error": "Username and password must be at least 3 characters."}, 400)
        if username.lower() in reserved_usernames():
            return self.json_response({"error": "That username is reserved."}, 400)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE lower(username) = lower(%s)",
                (username,),
            )
            if cursor.fetchone():
                return self.json_response({"error": "Username already exists."}, 409)

            cursor.execute(
                """
                INSERT INTO users (username, password, created_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (username, password, now_utc()),
            )
            user_id = cursor.fetchone()[0]
            seed_user_habits(connection, user_id)
            connection.commit()

        return self.json_response({"ok": True})

    def handle_login(self, headers, body):
        payload = self.read_json(body)
        username = payload.get("username", "").strip()
        password = payload.get("password", "").strip()
        role = payload.get("role", "").strip()

        session_data = None
        if role == "admin":
            if username == admin_username() and password == admin_password():
                session_data = {"role": "admin", "username": username}
        elif role == "user":
            with db_connection() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT id, username, password FROM users WHERE lower(username) = lower(%s)",
                    (username,),
                )
                user = row_to_dict(cursor)
            if user and password == user["password"]:
                session_data = {"role": "user", "username": user["username"], "user_id": user["id"]}

        if not session_data:
            return self.json_response({"error": "Invalid credentials for the selected role."}, 401)

        return self.json_response(
            {"authenticated": True, "role": session_data["role"]},
            headers=[("Set-Cookie", self.create_session(session_data, headers))],
        )

    def handle_logout(self, headers):
        return self.json_response(
            {"authenticated": False},
            headers=[("Set-Cookie", self.clear_session(headers))],
        )

    def handle_session(self, headers):
        session = self.current_session(headers)
        if not session:
            return self.json_response({"authenticated": False})
        return self.json_response(
            {"authenticated": True, "role": session["role"], "username": session["username"]}
        )

    def create_habit(self, session, body):
        payload = self.read_json(body)
        name = payload.get("name", "").strip()
        category = payload.get("category", "").strip()
        goal = payload.get("goal", "").strip()

        if not name or not category or not goal:
            return self.json_response({"error": "Name, category, and goal are required."}, 400)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO habits (user_id, name, category, goal, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (session["user_id"], name, category, goal, now_utc()),
            )
            connection.commit()
        return self.json_response({"ok": True})

    def toggle_habit(self, user_id, habit_id):
        if not self.user_owns_habit(user_id, habit_id):
            return self.json_response({"error": "Habit not found."}, 404)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM completions WHERE habit_id = %s AND completed_on = %s",
                (habit_id, today_key()),
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute("DELETE FROM completions WHERE id = %s", (existing[0],))
            else:
                cursor.execute(
                    "INSERT INTO completions (habit_id, completed_on) VALUES (%s, %s)",
                    (habit_id, today_key()),
                )
            connection.commit()
        return self.json_response({"ok": True})

    def clear_today(self, user_id, habit_id):
        if not self.user_owns_habit(user_id, habit_id):
            return self.json_response({"error": "Habit not found."}, 404)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "DELETE FROM completions WHERE habit_id = %s AND completed_on = %s",
                (habit_id, today_key()),
            )
            connection.commit()
        return self.json_response({"ok": True})

    def delete_habit(self, user_id, habit_id):
        if not self.user_owns_habit(user_id, habit_id):
            return self.json_response({"error": "Habit not found."}, 404)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM habits WHERE id = %s AND user_id = %s", (habit_id, user_id))
            connection.commit()
        return self.json_response({"ok": True})

    def seed_all_users(self):
        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM users")
            users = cursor.fetchall()
            for user in users:
                seed_user_habits(connection, user[0])
            connection.commit()
        return self.json_response({"ok": True})

    def reset_all_habits(self):
        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM completions")
            cursor.execute("DELETE FROM habits")
            connection.commit()
        return self.json_response({"ok": True})

    def delete_user_by_name(self, body):
        payload = self.read_json(body)
        username = payload.get("username", "").strip()

        if len(username) < 3:
            return self.json_response({"error": "Enter a valid username."}, 400)
        if username.lower() in reserved_usernames():
            return self.json_response({"error": "That account cannot be deleted."}, 400)

        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE lower(username) = lower(%s)",
                (username,),
            )
            existing = cursor.fetchone()
            if not existing:
                return self.json_response({"error": "User not found."}, 404)

            cursor.execute("DELETE FROM users WHERE id = %s", (existing[0],))
            connection.commit()

        return self.json_response({"ok": True})

    def handle(self, method, path, headers, body=b""):
        path = urlparse(path).path

        try:
            self.ensure_database()
        except Exception as error:
            return self.json_response(
                {
                    "error": "Backend configuration error.",
                    "details": str(error),
                },
                500,
            )

        if method == "GET" and path == "/api/session":
            return self.handle_session(headers)
        if method == "GET" and path == "/api/user/dashboard":
            session, error = self.require_role(headers, "user")
            return error or self.json_response(user_dashboard_payload(session["user_id"]))
        if method == "GET" and path == "/api/admin/dashboard":
            session, error = self.require_role(headers, "admin")
            return error or self.json_response(admin_dashboard_payload())

        if method == "POST" and path == "/api/register":
            return self.handle_register(body)
        if method == "POST" and path == "/api/login":
            return self.handle_login(headers, body)
        if method == "POST" and path == "/api/logout":
            return self.handle_logout(headers)
        if method == "POST" and path == "/api/habits":
            session, error = self.require_role(headers, "user")
            return error or self.create_habit(session, body)
        if method == "POST" and path.startswith("/api/habits/") and path.endswith("/toggle"):
            session, error = self.require_role(headers, "user")
            return error or self.toggle_habit(session["user_id"], self.extract_habit_id(path))
        if method == "POST" and path.startswith("/api/habits/") and path.endswith("/clear_today"):
            session, error = self.require_role(headers, "user")
            return error or self.clear_today(session["user_id"], self.extract_habit_id(path))
        if method == "POST" and path == "/api/admin/seed":
            _, error = self.require_role(headers, "admin")
            return error or self.seed_all_users()
        if method == "POST" and path == "/api/admin/reset":
            _, error = self.require_role(headers, "admin")
            return error or self.reset_all_habits()
        if method == "POST" and path == "/api/admin/delete_user":
            _, error = self.require_role(headers, "admin")
            return error or self.delete_user_by_name(body)

        if method == "DELETE" and path.startswith("/api/habits/"):
            session, error = self.require_role(headers, "user")
            return error or self.delete_habit(session["user_id"], self.extract_habit_id(path))

        return self.json_response({"error": "Not found."}, 404)
