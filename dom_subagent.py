"""
tools/dom_subagent.py — AI-powered DOM element finder
Uses Claude Haiku to locate complex elements by description
"""
import os
import anthropic
from config.system_prompts import DOM_AGENT_PROMPT


async def find_element(page_content: str, description: str) -> str:
    """
    Uses AI to find a CSS selector for an element by its description.
    Returns selector string or empty string if not found.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"""Page content (fragment):
{page_content[:3000]}

Find element: {description}
Return only the CSS selector."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=DOM_AGENT_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip().strip('"\'')
    except Exception:
        return ""
