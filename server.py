"""
server.py — FastAPI server: Web Dashboard + REST API + WebSocket
"""
import os
import json
import hashlib
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import database as db
from utils import logger as agent_logger
from agent_core import run_task


# ── WebSocket connection manager ──
class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, username: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(username, []).append(ws)

    def disconnect(self, username: str, ws: WebSocket):
        if username in self.connections:
            try:
                self.connections[username].remove(ws)
            except ValueError:
                pass

    async def send_to_user(self, username: str, message: str):
        for ws in self.connections.get(username, []):
            try:
                await ws.send_text(message)
            except Exception:
                pass

    async def broadcast_to_all(self, message: str):
        for connections in self.connections.values():
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    pass


manager = ConnectionManager()


async def broadcast_fn(username: str, message: str):
    await manager.send_to_user(username, message)
    # Also send to admin so they see all tasks live
    if username != "admin":
        await manager.send_to_user("admin", message)


agent_logger.set_broadcast(broadcast_fn)


# ── Startup / Shutdown ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await load_sessions()
    print("✅ Database initialized")
    print(f"✅ Restored {len(active_sessions)} active session(s)")
    print("✅ Server running at http://localhost:8000")
    yield
    print("Server stopped")


app = FastAPI(title="Browser Agent Dashboard", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Session store (in-memory + persisted to DB) ──
active_sessions: dict[str, dict] = {}


async def load_sessions():
    """Load sessions from DB on startup (survives --reload)"""
    import aiosqlite
    try:
        async with aiosqlite.connect("data/agent.db") as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT,
                    display_name TEXT,
                    color TEXT
                )
            """)
            await conn.commit()
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM sessions")
            rows = await cursor.fetchall()
            for r in rows:
                active_sessions[r["token"]] = dict(r)
    except Exception as e:
        print(f"[sessions] Could not load: {e}")


async def save_session(token: str, session: dict):
    import aiosqlite
    try:
        async with aiosqlite.connect("data/agent.db") as conn:
            await conn.execute("""
                INSERT OR REPLACE INTO sessions (token, user_id, username, role, display_name, color)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token, session["id"], session["username"], session["role"],
                  session["display_name"], session["color"]))
            await conn.commit()
    except Exception as e:
        print(f"[sessions] Could not save: {e}")


async def delete_session(token: str):
    import aiosqlite
    try:
        async with aiosqlite.connect("data/agent.db") as conn:
            await conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            await conn.commit()
    except Exception:
        pass


# ── Routes ──

@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.post("/api/login")
async def login(data: dict):
    username = data.get("username", "").lower().strip()
    password = data.get("password", "")
    user = await db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user["password_hash"] != hashlib.sha256(password.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid password")
    import uuid
    token = uuid.uuid4().hex
    session = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
        "color": user["color"],
    }
    active_sessions[token] = session
    await save_session(token, session)
    return {"token": token, "user": session}


@app.post("/api/logout")
async def logout(data: dict):
    token = data.get("token", "")
    active_sessions.pop(token, None)
    await delete_session(token)
    return {"status": "ok"}


@app.post("/api/run")
async def api_run_task(data: dict):
    session = active_sessions.get(data.get("token", ""))
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    task_text = data.get("task", "").strip()
    if not task_text:
        raise HTTPException(status_code=400, detail="Task cannot be empty")
    task_id = await run_task(task_text, session["id"], session["username"])
    return {"task_id": task_id, "status": "started"}


@app.get("/api/tasks")
async def api_get_tasks(token: str, username: str = None):
    session = active_sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if session["role"] == "admin":
        tasks = await db.get_all_tasks()
        if username and username != "all":
            tasks = [t for t in tasks if t["username"] == username]
    else:
        tasks = await db.get_tasks_for_user(session["username"])
    return tasks


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str, token: str):
    session = active_sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    all_tasks = await db.get_all_tasks()
    task = next((t for t in all_tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if session["role"] != "admin" and task["username"] != session["username"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return task


@app.get("/api/users")
async def api_get_users(token: str):
    session = active_sessions.get(token)
    if not session or session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    users = await db.get_all_users()
    result = []
    for u in users:
        stats = await db.get_user_stats(u["username"])
        result.append({**u, **stats})
    return result


@app.get("/api/stats")
async def api_get_stats(token: str):
    session = active_sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    stats = await db.get_user_stats(session["username"])
    if session["role"] == "admin":
        all_tasks = await db.get_all_tasks()
        stats["system_total"] = len(all_tasks)
        stats["system_users"] = len(set(t["username"] for t in all_tasks))
    return stats


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    await websocket.accept()

    session = active_sessions.get(token)
    if not session:
        try:
            await websocket.send_text('{"type":"ERR","message":"Session expired. Please log in again."}')
        except Exception:
            pass
        await websocket.close(code=1008)
        return

    username = session["username"]
    manager.connections.setdefault(username, []).append(websocket)

    # Send confirmation that WS is live
    try:
        await websocket.send_text(json.dumps({
            "type": "SYS",
            "message": f"Connected as {username}",
            "time": "00:00:00"
        }))
    except Exception:
        pass

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive ping to browser
                try:
                    await websocket.send_text('{"type":"ping"}')
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Error for {username}: {e}")
    finally:
        manager.disconnect(username, websocket)
