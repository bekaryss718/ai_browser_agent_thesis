"""
database.py — SQLite database (users + tasks)
"""
import aiosqlite
import hashlib
import os
import json
from datetime import datetime

DB_PATH = "data/agent.db"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


async def init_db():
    """Initialize database and create tables"""
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                display_name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#7c5cfc',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                task_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                steps INTEGER DEFAULT 0,
                duration_sec INTEGER,
                logs TEXT DEFAULT '[]',
                result TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        await db.commit()

        # Create 3 default users
        users = [
            ("admin", hash_password("admin123"), "admin", "Admin", "#ff9500"),
            ("alice", hash_password("alice123"), "user",  "Alice", "#7c5cfc"),
            ("bob",   hash_password("bob123"),   "user",  "Bob",   "#00e5ff"),
        ]
        for username, pw_hash, role, display_name, color in users:
            try:
                await db.execute(
                    "INSERT INTO users (username, password_hash, role, display_name, color, created_at) VALUES (?,?,?,?,?,?)",
                    (username, pw_hash, role, display_name, color, datetime.now().isoformat())
                )
            except Exception:
                pass

        # Add sample tasks if table is empty
        cursor = await db.execute("SELECT COUNT(*) FROM tasks")
        count = (await cursor.fetchone())[0]
        if count == 0:
            sample_tasks = [
                ("task_001", 1, "admin",
                 "Find Python developer jobs in New York on LinkedIn",
                 "done", 12, 45,
                 json.dumps([
                     {"t": "SYS",   "m": "Agent started"},
                     {"t": "THINK", "m": "Task: search Python jobs on LinkedIn"},
                     {"t": "ACT",   "m": "navigate → https://linkedin.com/jobs"},
                     {"t": "OBS",   "m": "Page loaded: LinkedIn Jobs"},
                     {"t": "ACT",   "m": 'type → search field: "Python developer New York"'},
                     {"t": "ACT",   "m": "click → Search button"},
                     {"t": "OBS",   "m": "Found: 3,421 job listings"},
                     {"t": "THINK", "m": "Collecting first 5 results"},
                     {"t": "SYS",   "m": "✅ Task completed in 45 seconds"},
                 ]),
                 "Found 3421 Python jobs", "2024-01-10T10:00:00", "2024-01-10T10:00:45"),

                ("task_002", 2, "alice",
                 "Go to gmail.com and find emails from Uber",
                 "done", 8, 28,
                 json.dumps([
                     {"t": "SYS",   "m": "Agent started"},
                     {"t": "THINK", "m": "Task: find Uber emails in Gmail"},
                     {"t": "ACT",   "m": "navigate → https://gmail.com"},
                     {"t": "OBS",   "m": "Gmail loaded"},
                     {"t": "ACT",   "m": 'type → search: "from:uber"'},
                     {"t": "OBS",   "m": "Found 23 emails from Uber"},
                     {"t": "SYS",   "m": "✅ Task completed"},
                 ]),
                 "Found 23 emails", "2024-01-11T14:00:00", "2024-01-11T14:00:28"),

                ("task_003", 3, "bob",
                 "Check USD to EUR exchange rate on xe.com",
                 "done", 5, 12,
                 json.dumps([
                     {"t": "SYS",   "m": "Agent started"},
                     {"t": "ACT",   "m": "navigate → https://xe.com"},
                     {"t": "OBS",   "m": "XE Currency page loaded"},
                     {"t": "ACT",   "m": "get_content → extracting rates"},
                     {"t": "OBS",   "m": "1 USD = 0.92 EUR"},
                     {"t": "SYS",   "m": "✅ Task completed"},
                 ]),
                 "1 USD = 0.92 EUR", "2024-01-12T09:00:00", "2024-01-12T09:00:12"),
            ]
            for t in sample_tasks:
                await db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)", t)
        await db.commit()


async def get_user_by_username(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE username=?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, username, role, display_name, color, created_at FROM users")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_task(task_id: str, user_id: int, username: str, task_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tasks (id, user_id, username, task_text, status, steps, logs, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (task_id, user_id, username, task_text, "running", 0, "[]", datetime.now().isoformat())
        )
        await db.commit()


async def update_task(task_id: str, status: str, steps: int, duration: int, logs: list, result: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET status=?, steps=?, duration_sec=?, logs=?, result=?, finished_at=? WHERE id=?",
            (status, steps, duration, json.dumps(logs), result, datetime.now().isoformat(), task_id)
        )
        await db.commit()


async def get_tasks_for_user(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE username=? ORDER BY created_at DESC", (username,)
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["logs"] = json.loads(d["logs"] or "[]")
            result.append(d)
        return result


async def get_all_tasks():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["logs"] = json.loads(d["logs"] or "[]")
            result.append(d)
        return result


async def get_user_stats(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE username=?", (username,))
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE username=? AND status='done'", (username,))
        done = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE username=? AND status='failed'", (username,))
        failed = (await cursor.fetchone())[0]
        return {"total": total, "done": done, "failed": failed}
