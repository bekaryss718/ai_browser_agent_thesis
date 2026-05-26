"""
utils/logger.py — Agent logger with WebSocket broadcast support
"""
import json
from datetime import datetime
from typing import Callable, Optional

_broadcast_fn: Optional[Callable] = None


def set_broadcast(fn: Callable):
    global _broadcast_fn
    _broadcast_fn = fn


class AgentLogger:
    def __init__(self, task_id: str, username: str):
        self.task_id = task_id
        self.username = username
        self.logs: list[dict] = []

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def log(self, log_type: str, message: str):
        entry = {"t": log_type, "m": message}
        self.logs.append(entry)
        payload = {
            "task_id": self.task_id,
            "type": log_type,
            "message": message,
            "time": self._now()
        }
        print(f"[{log_type}] {message}")
        if _broadcast_fn:
            try:
                await _broadcast_fn(self.username, json.dumps(payload))
            except Exception:
                pass

    async def think(self, msg: str): await self.log("THINK", msg)
    async def act(self, msg: str):   await self.log("ACT",   msg)
    async def obs(self, msg: str):   await self.log("OBS",   msg)
    async def err(self, msg: str):   await self.log("ERR",   msg)
    async def sys(self, msg: str):   await self.log("SYS",   msg)
