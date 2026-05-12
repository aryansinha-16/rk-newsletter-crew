#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RK Group Daily Intelligence Newsletter
Plain Python + Anthropic API (no CrewAI)
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
import anthropic

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MCP_URL = "https://valuecart-email-mcp-production.up.railway.app/mcp/valuecart2026"

COMPANIES = [
    "Amazon India",
    "Flipkart",
    "Myntra",
    "PharmEasy",
    "Nike India",
    "Blinkit",
    "Aditya Birla Group",
    "Cars24",
    "Scapia",
    "Smytten",
    "India China Relations",
]

RK_GROUP_CONTEXT = """RK Group is a brand distribution and retail business with interests in:
- Fashion and apparel distribution (including Nike partnership via Westbury)
- D2C brand building and marketplace management
- Health and wellness category
- Last-mile logistics and quick commerce
Focus on news that is directly actionable or reveals competitive intelligence relevant to these areas."""

RSS_FEEDS = {
    "Inc42": "https://inc42.com/feed/",
    "YourStory": "https://yourstory.com/feed",
    "Entrackr": "https://entrackr.com/feed/",
    "Mint": "https://www.livemint.com/rss/news",
}

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _search_news(query: str) -> str:
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


def _fetch_rss_news(company: str) -> str:
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
                    if parsedate_to_datetime(pub_date) < cutoff:
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
    return "\n\n---\n\n".join(results[:5]) if results else f"No RSS results found for {company}."


def _send_email(to: str, subject: str, body_html: str) -> str:
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    results = []
    for recipient in recipients:
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "send_email",
                    "arguments": {"to": recipient, "subject": subject, "body_html": body_html},
                },
            }
            resp = requests.post(
                MCP_URL,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
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
                results.append(f"{recipient}: Failed — {result_data['error']}")
            else:
                results.append(f"{recipient}: Sent")
        except Exception as e:
            results.append(f"{recipient}: Failed — {e}")
    return "\n".join(results)


def dispatch_tool(name: str, inputs: dict) -> str:
    if name == "search_news":
        return _search_news(inputs["query"])
    if name == "fetch_rss_news":
        return _fetch_rss_news(inputs["company"])
    if name == "send_email":
        return _send_email(inputs["to"], inputs["subject"], inputs["body_html"])
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Tool schemas for Anthropic API
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_news",
        "description": "Search Google News for recent articles about a company or topic (past 2 days). Returns real articles with verified URLs only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query, e.g. 'Flipkart India news'"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_rss_news",
        "description": "Fetch recent news about a company from Indian business RSS feeds (Inc42, YourStory, Entrackr, Mint). Only returns articles from the past 2 days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name to search for"}
            },
            "required": ["company"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an HTML email to one or more recipients via SendGrid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Comma-separated recipient email addresses"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body_html": {"type": "string", "description": "Full HTML body of the email"},
            },
            "required": ["to", "subject", "body_html"],
        },
    },
]

# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------

def run_agent(system: str, user_prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages = [{"role": "user", "content": user_prompt}]

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect any text output
        text_output = ""
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_output += block.text
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return text_output

        if response.stop_reason == "tool_use":
            tool_results = []
            for tu in tool_uses:
                print(f"  [tool] {tu.name}({json.dumps(tu.input)[:80]}...)")
                result = dispatch_tool(tu.name, tu.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return text_output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_newsletter():
    recipients_env = os.getenv("NEWSLETTER_RECIPIENTS", "aryan@valuecart.in")
    recipients = [r.strip() for r in recipients_env.split(",") if r.strip()]
    recipient_str = ", ".join(recipients)
    today = datetime.now().strftime("%B %d, %Y")
    company_list = "\n".join(f"- {c}" for c in COMPANIES)

    print(f"\n{'='*60}")
    print(f"RK Group Daily Newsletter")
    print(f"Date      : {today}")
    print(f"Recipients: {recipient_str}")
    print(f"{'='*60}\n")

    system = (
        "You are an AI that produces a daily business intelligence newsletter for RK Group. "
        "You have tools to search news and send email. Be concise and factual. "
        "Only include news from the past 2 days. If no recent news exists for a company, say so."
    )

    prompt = f"""Today is {today}. Produce and send the RK Group Daily Intelligence Newsletter.

COMPANIES TO RESEARCH:
{company_list}

RK GROUP CONTEXT:
{RK_GROUP_CONTEXT}

STEPS:
1. For each company, use search_news and fetch_rss_news to find news from the past 2 days.
2. Write a clean HTML newsletter email with:
   - Subject: "RK Intelligence | {today} | [1-line hook from top story]"
   - Header: "RK Group Intelligence" + date
   - Executive Summary: 3 most important things today
   - One section per company with 2-3 bullets: what happened + why it matters
   - Skip companies with no news today (write "No major news today.")
   - Footer: "RK Group Intelligence | {today} | Confidential"
   - Clean white background, Arial font, mobile-friendly inline styles
3. Send the email to: {recipient_str}

Write the newsletter directly in the send_email call — do not return it as text."""

    result = run_agent(system, prompt)
    print("\nDone.")
    if result:
        print(result)


if __name__ == "__main__":
    run_newsletter()
