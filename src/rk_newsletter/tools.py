import os
import json
import requests
from crewai.tools import tool

MCP_URL = "https://valuecart-email-mcp-production.up.railway.app/mcp/valuecart2026"


@tool("Search recent news")
def search_news(query: str) -> str:
    """Search Google News for recent articles about a company or topic (past 7 days)."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return "ERROR: SERPER_API_KEY not set."
    try:
        resp = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5, "tbs": "qdr:w", "gl": "in", "hl": "en"},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("news", [])[:5]
        if not items:
            return "No recent news found."
        results = []
        for item in items:
            results.append(
                f"TITLE: {item.get('title', '')}\n"
                f"SOURCE: {item.get('source', '')} | DATE: {item.get('date', '')}\n"
                f"SNIPPET: {item.get('snippet', '')}"
            )
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Search failed: {e}"


@tool("Send email via SendGrid")
def send_email(to: str, subject: str, body_html: str) -> str:
    """Send an HTML email via the Railway SendGrid MCP server."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "send_email",
            "arguments": {
                "to": to,
                "subject": subject,
                "body_html": body_html,
            },
        },
    }
    try:
        resp = requests.post(
            MCP_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=30,
            stream=True,
        )
        resp.raise_for_status()

        result_data = None
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line
            if decoded.startswith("data:"):
                data_str = decoded[5:].strip()
                if data_str:
                    try:
                        result_data = json.loads(data_str)
                    except Exception:
                        pass

        if result_data and "error" in result_data:
            return f"Failed: {result_data['error']}"

        return f"Email sent successfully to: {to}"
    except Exception as e:
        return f"Send failed: {e}"
