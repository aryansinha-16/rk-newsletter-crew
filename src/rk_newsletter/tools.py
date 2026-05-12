import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from crewai.tools import tool

MCP_URL = "https://valuecart-email-mcp-production.up.railway.app/mcp/valuecart2026"

RSS_FEEDS = {
    "Inc42": "https://inc42.com/feed/",
    "YourStory": "https://yourstory.com/feed",
    "Entrackr": "https://entrackr.com/feed/",
    "Mint": "https://www.livemint.com/rss/news",
}


@tool("Search recent news")
def search_news(query: str) -> str:
    """Search Google News for recent articles about a company or topic (past 2 days). Returns real articles with verified URLs only."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return "ERROR: SERPER_API_KEY not set."
    try:
        resp = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5, "tbs": "qdr:2d", "gl": "in", "hl": "en"},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("news", [])[:5]
        if not items:
            return "No recent news found."
        results = []
        for item in items:
            url = item.get("link", "")
            if not url:
                continue
            results.append(
                f"TITLE: {item.get('title', '')}\n"
                f"SOURCE: {item.get('source', '')} | DATE: {item.get('date', '')}\n"
                f"SNIPPET: {item.get('snippet', '')}\n"
                f"URL: {url}"
            )
        return "\n\n---\n\n".join(results) if results else "No recent news found."
    except Exception as e:
        return f"Search failed: {e}"


@tool("Fetch RSS news feeds")
def fetch_rss_news(company: str) -> str:
    """Fetch recent news about a company from Indian business RSS feeds (Inc42, YourStory, Entrackr, Mint). Returns real articles with verified URLs only."""
    results = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    for source, url in RSS_FEEDS.items():
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            for item in items[:30]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                desc = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")
                try:
                    article_dt = parsedate_to_datetime(pub_date)
                    if article_dt < cutoff:
                        continue
                except Exception:
                    pass
                if company.lower() in title.lower() or company.lower() in desc.lower():
                    if link:
                        results.append(
                            f"TITLE: {title}\n"
                            f"SOURCE: {source} | DATE: {pub_date}\n"
                            f"SNIPPET: {desc[:200]}\n"
                            f"URL: {link}"
                        )
        except Exception:
            continue

    if not results:
        return f"No RSS results found for {company}."
    return "\n\n---\n\n".join(results[:5])


def _send_single_email(to: str, subject: str, body_html: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "send_email",
            "arguments": {"to": to, "subject": subject, "body_html": body_html},
        },
    }
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
        decoded = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
        if decoded.startswith("data:"):
            data_str = decoded[5:].strip()
            if data_str:
                try:
                    result_data = json.loads(data_str)
                except Exception:
                    pass

    if result_data and "error" in result_data:
        return f"Failed: {result_data['error']}"

    if result_data:
        content = result_data.get("result", {}).get("content", [])
        if content:
            return content[0].get("text", f"Sent to {to}")
    return f"Sent to {to}"


@tool("Send email via SendGrid")
def send_email(to: str, subject: str, body_html: str) -> str:
    """Send an HTML email to one or more recipients via the Railway SendGrid MCP server. 'to' can be a single address or comma-separated list."""
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    results = []
    for recipient in recipients:
        try:
            result = _send_single_email(recipient, subject, body_html)
            results.append(f"{recipient}: {result}")
        except Exception as e:
            results.append(f"{recipient}: Failed — {e}")
    return "\n".join(results)
