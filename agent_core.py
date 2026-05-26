"""
agent_core.py — Main agent logic (ReAct loop)
"""
import os
import json
import time
import uuid
import asyncio
from typing import Optional

import anthropic

from config.system_prompts import MAIN_AGENT_PROMPT
from utils.mcp_client import MCPClient
from utils.logger import AgentLogger
from tools.browser_tools import BrowserTools
from database import create_task, update_task

MODEL_PRIMARY  = "claude-sonnet-4-6"
MODEL_FALLBACK = "claude-haiku-4-5-20251001"

_mcp_instance: Optional[MCPClient] = None
_mcp_lock = asyncio.Lock()


async def get_mcp() -> Optional[MCPClient]:
    global _mcp_instance
    async with _mcp_lock:
        # Check if existing instance is still alive
        if _mcp_instance is not None:
            if _mcp_instance.process and _mcp_instance.process.returncode is None:
                return _mcp_instance
            else:
                # Process died, reset and retry
                _mcp_instance = None

        # Try to connect
        mcp = MCPClient()
        ok = await mcp.connect()
        if ok:
            _mcp_instance = mcp
            return _mcp_instance
        return None


class BrowserAgent:
    def __init__(self, task_id: str, user_id: int, username: str, task_text: str):
        self.task_id = task_id
        self.user_id = user_id
        self.username = username
        self.task_text = task_text
        self.logger = AgentLogger(task_id, username)
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = MODEL_PRIMARY
        self.max_steps = 20
        self.messages = []
        self.steps = 0
        self.start_time = None
        self.loop_detector: list[str] = []

    async def run(self) -> dict:
        self.start_time = time.time()
        await self.logger.sys(f"🤖 Agent started. Task: {self.task_text[:80]}...")
        await create_task(self.task_id, self.user_id, self.username, self.task_text)

        await self.logger.sys("🔌 Connecting to browser...")
        try:
            mcp = await get_mcp()
            if mcp is None:
                await self.logger.err(
                    "❌ Failed to connect to browser (MCP). "
                    "Check server console for details — look for [MCP] lines."
                )
                await update_task(self.task_id, "failed", 0, 0, self.logger.logs, None)
                return {"status": "failed", "result": "MCP connection failed"}
            await self.logger.sys("✅ Browser connected!")
            browser = BrowserTools(mcp, self.logger)
        except Exception as e:
            await self.logger.err(f"❌ Browser error: {e}")
            await update_task(self.task_id, "failed", 0, 0, self.logger.logs, None)
            return {"status": "failed", "result": str(e)}

        self.messages = [{
            "role": "user",
            "content": f"Task: {self.task_text}\n\nStart execution. First navigate to the relevant website."
        }]

        result_text = None
        final_status = "failed"

        for step in range(self.max_steps):
            self.steps = step + 1
            await self.logger.think(f"Step {self.steps}/{self.max_steps}")

            try:
                response_text = await self._call_claude()
            except Exception as e:
                await self.logger.err(f"Claude API error: {e}")
                break

            try:
                raw = response_text.strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                data = json.loads(raw)
            except Exception:
                await self.logger.obs(response_text[:200])
                result_text = response_text
                final_status = "done"
                break

            thought     = data.get("thought", "")
            action      = data.get("action", "")
            action_input = data.get("action_input", "")

            if thought:
                await self.logger.think(thought[:150])

            sig = f"{action}:{action_input[:50]}"
            if self.loop_detector.count(sig) >= 3:
                await self.logger.err("⚠️ Loop detected! Stopping.")
                break
            self.loop_detector.append(sig)

            obs = ""
            if action == "done":
                result_text = action_input
                final_status = "done"
                await self.logger.sys(f"✅ Task completed: {action_input[:100]}")
                break
            elif action == "need_confirmation":
                await self.logger.sys(f"⚠️ Requires confirmation: {action_input}")
                result_text = f"Requires confirmation: {action_input}"
                final_status = "failed"
                break
            elif action == "navigate":
                obs = await browser.navigate(action_input)
            elif action == "click":
                obs = await browser.click(action_input)
            elif action == "type":
                if "|||" in action_input:
                    sel, text = action_input.split("|||", 1)
                    obs = await browser.type_text(sel.strip(), text.strip())
                else:
                    obs = await browser.type_text(action_input, "")
            elif action == "get_content":
                obs = await browser.get_page_content()
            elif action == "screenshot":
                obs = await browser.screenshot()
            elif action == "evaluate":
                obs = await browser.evaluate(action_input)
            elif action == "scroll":
                obs = await browser.scroll("down" if "down" in action_input.lower() else "up")
            else:
                obs = f"Unknown action: {action}"
                await self.logger.err(obs)

            self.messages.append({"role": "assistant", "content": response_text})
            self.messages.append({"role": "user", "content": f"Action result: {obs[:1000]}\n\nContinue."})
            await asyncio.sleep(0.5)

        duration = int(time.time() - self.start_time)
        await update_task(self.task_id, final_status, self.steps, duration, self.logger.logs, result_text)

        if final_status == "done":
            await self.logger.sys(f"🏁 Finished in {duration}s, {self.steps} steps")
        else:
            await self.logger.err(f"❌ Failed after {duration}s")

        return {"status": final_status, "result": result_text, "steps": self.steps, "duration": duration}

    async def _call_claude(self) -> str:
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=MAIN_AGENT_PROMPT,
                    messages=self.messages[-20:]
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                if self.model == MODEL_PRIMARY:
                    await self.logger.sys(f"⚠️ Rate limit, switching to {MODEL_FALLBACK}")
                    self.model = MODEL_FALLBACK
                else:
                    await self.logger.sys("⚠️ Rate limit, waiting 10s...")
                    await asyncio.sleep(10)
            except anthropic.APIError as e:
                await self.logger.err(f"API error: {e}")
                raise
        raise Exception("All API retries exhausted")


async def run_task(task_text: str, user_id: int, username: str) -> str:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    agent = BrowserAgent(task_id, user_id, username, task_text)
    asyncio.create_task(agent.run())
    return task_id
