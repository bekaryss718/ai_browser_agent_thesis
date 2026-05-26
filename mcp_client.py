"""
utils/mcp_client.py — MCP Client, Windows-compatible
"""
import asyncio
import json
import sys
import shutil
import os
from typing import Optional


def _find_npx() -> Optional[str]:
    """Find npx executable, trying all Windows variants"""
    candidates = ["npx.cmd", "npx.exe", "npx"]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    # Try common install paths on Windows
    appdata = os.environ.get("APPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    paths = [
        os.path.join(appdata, "npm", "npx.cmd"),
        os.path.join(program_files, "nodejs", "npx.cmd"),
        "C:\\Program Files\\nodejs\\npx.cmd",
        "C:\\Program Files (x86)\\nodejs\\npx.cmd",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _find_node_module() -> Optional[str]:
    """Find the installed server-puppeteer index.js directly"""
    appdata = os.environ.get("APPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

    candidates = [
        # Global npm on Windows
        os.path.join(appdata, "npm", "node_modules",
                     "@modelcontextprotocol", "server-puppeteer", "dist", "index.js"),
        os.path.join(program_files, "nodejs", "node_modules",
                     "@modelcontextprotocol", "server-puppeteer", "dist", "index.js"),
        # Linux/mac global
        "/usr/local/lib/node_modules/@modelcontextprotocol/server-puppeteer/dist/index.js",
        "/usr/lib/node_modules/@modelcontextprotocol/server-puppeteer/dist/index.js",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _build_cmd() -> list[str]:
    """Build the command to launch MCP puppeteer server"""

    # Option 1: run index.js directly with node (most reliable on Windows)
    module_path = _find_node_module()
    if module_path:
        node = shutil.which("node") or "node"
        print(f"[MCP] Using direct node path: {module_path}", file=sys.stderr)
        return [node, module_path]

    # Option 2: npx.cmd (Windows)
    npx = _find_npx()
    if npx:
        print(f"[MCP] Using npx: {npx}", file=sys.stderr)
        return [npx, "-y", "@modelcontextprotocol/server-puppeteer"]

    # Option 3: cmd /c npx (fallback for Windows)
    if sys.platform == "win32":
        print("[MCP] Using cmd /c npx fallback", file=sys.stderr)
        return ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-puppeteer"]

    return ["npx", "-y", "@modelcontextprotocol/server-puppeteer"]


class MCPClient:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self.available_tools: list[dict] = []

    async def connect(self) -> bool:
        cmd = _build_cmd()
        print(f"[MCP] Launching: {' '.join(cmd)}", file=sys.stderr)
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for process to initialize
            await asyncio.sleep(3)

            if self.process.returncode is not None:
                err_bytes = await self.process.stderr.read(4096)
                print(f"[MCP] Process died. stderr:\n{err_bytes.decode(errors='replace')}", file=sys.stderr)
                return False

            self._reader_task = asyncio.create_task(self._read_loop())

            # Handshake
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "browser-agent", "version": "1.0.0"}
            })
            result = await self._send_request("tools/list", {})
            self.available_tools = result.get("tools", [])
            names = [t["name"] for t in self.available_tools]
            print(f"[MCP] ✅ Connected! Tools: {names}", file=sys.stderr)
            return True

        except asyncio.TimeoutError:
            print("[MCP] ❌ Timeout during handshake", file=sys.stderr)
            await self._dump_stderr()
            return False
        except Exception as e:
            import traceback
            print(f"[MCP] ❌ Exception: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            await self._dump_stderr()
            return False

    async def _dump_stderr(self):
        if self.process:
            try:
                err = await asyncio.wait_for(self.process.stderr.read(4096), timeout=2)
                if err:
                    print(f"[MCP] Process stderr: {err.decode(errors='replace')}", file=sys.stderr)
            except Exception:
                pass

    async def _read_loop(self):
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                raw = line.decode(errors="replace").strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # skip non-JSON startup messages
                req_id = data.get("id")
                if req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        if "error" in data:
                            fut.set_exception(Exception(str(data["error"])))
                        else:
                            fut.set_result(data.get("result", {}))
            except Exception:
                break

    async def _send_request(self, method: str, params: dict) -> dict:
        self.request_id += 1
        rid = self.request_id
        payload = json.dumps({
            "jsonrpc": "2.0", "id": rid,
            "method": method, "params": params
        }) + "\n"
        fut = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        self.process.stdin.write(payload.encode())
        await self.process.stdin.drain()
        return await asyncio.wait_for(fut, timeout=30.0)

    async def call_tool(self, name: str, args: dict) -> str:
        try:
            result = await self._send_request("tools/call", {"name": name, "arguments": args})
            content = result.get("content", [])
            return "\n".join(c["text"] for c in content if c.get("type") == "text") or "OK"
        except asyncio.TimeoutError:
            return "ERROR: Timeout"
        except Exception as e:
            return f"ERROR: {e}"

    async def navigate(self, url: str) -> str:
        return await self.call_tool("puppeteer_navigate", {"url": url})

    async def screenshot(self) -> str:
        return await self.call_tool("puppeteer_screenshot", {"name": "screen", "fullPage": False})

    async def click(self, selector: str) -> str:
        return await self.call_tool("puppeteer_click", {"selector": selector})

    async def type_text(self, selector: str, text: str) -> str:
        return await self.call_tool("puppeteer_fill", {"selector": selector, "value": text})

    async def evaluate(self, script: str) -> str:
        return await self.call_tool("puppeteer_evaluate", {"script": script})

    async def get_page_content(self) -> str:
        return await self.evaluate("""(function(){
            var c=document.body.cloneNode(true);
            c.querySelectorAll('script,style,noscript').forEach(s=>s.remove());
            return c.innerText.substring(0,4000);
        })()""")

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
