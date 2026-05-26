"""
tools/browser_tools.py — Browser control tools
Smart click logic: Native -> Coordinates -> JS Injection
"""
from utils.mcp_client import MCPClient
from utils.logger import AgentLogger


class BrowserTools:
    def __init__(self, mcp: MCPClient, logger: AgentLogger):
        self.mcp = mcp
        self.logger = logger

    async def navigate(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        await self.logger.act(f"navigate → {url}")
        result = await self.mcp.navigate(url)
        await self.logger.obs(f"Page loaded: {url}")
        return result

    async def click(self, selector: str) -> str:
        """Smart click: native first, then JS fallback"""
        await self.logger.act(f"click → {selector}")
        result = await self.mcp.click(selector)
        if "ERROR" not in result:
            await self.logger.obs("Click successful")
            return result
        await self.logger.think("Native click failed, trying JS injection...")
        js_result = await self.mcp.evaluate(f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (el) {{ el.click(); return 'clicked via JS'; }}
                return 'element not found';
            }})()
        """)
        await self.logger.obs(f"JS click: {js_result}")
        return js_result

    async def type_text(self, selector: str, text: str) -> str:
        await self.logger.act(f'type → {selector}: "{text[:50]}"')
        result = await self.mcp.type_text(selector, text)
        await self.logger.obs("Text entered")
        return result

    async def get_page_content(self) -> str:
        await self.logger.act("get_page_content → extracting page text")
        content = await self.mcp.get_page_content()
        await self.logger.obs(f"Received {len(content)} characters")
        return content

    async def screenshot(self) -> str:
        await self.logger.act("screenshot → capturing screen")
        result = await self.mcp.screenshot()
        await self.logger.obs("Screenshot taken")
        return result

    async def scroll(self, direction: str = "down", amount: int = 3) -> str:
        px = amount * 300
        script = f"window.scrollBy(0, {px if direction == 'down' else -px})"
        await self.logger.act(f"scroll → {direction} by {amount} screens")
        await self.mcp.evaluate(script)
        await self.logger.obs("Scroll complete")
        return "scrolled"

    async def evaluate(self, script: str) -> str:
        await self.logger.act(f"evaluate → {script[:80]}")
        result = await self.mcp.evaluate(script)
        await self.logger.obs(f"Result: {str(result)[:200]}")
        return result
