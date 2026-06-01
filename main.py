#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RK Group Daily Intelligence Newsletter
Plain Python + Anthropic API (no CrewAI)
"""

import os
import sys
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
import anthropic

import history as hist

load_dotenv()
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)

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
# Run-scoped state
# ---------------------------------------------------------------------------

# Every article surfaced this run, keyed by URL → title. Used to map the URLs
# that end up in the sent email back to their headlines for the history store.
CANDIDATES: dict[str, str] = {}

# Stories actually included in the email that went out (filled by _send_email).
SENT_STORIES: list[dict] = []

# Normalized headline keys already emailed in the retention window. Used to
# pre-filter search/RSS results so the model never even sees old stories.
SENT_KEYS: set[str] = set()


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
            json={"q": query, "num": 5, "tbs": "qdr:1d", "gl": "in", "hl": "en"},
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
            title = item.get("title", "")
            if hist.normalize_headline(title) in SENT_KEYS:
                continue  # already emailed in the last 10 days
            CANDIDATES[url] = title
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
                    continue  # unparseable date → can't confirm it's recent, skip it
                if company.lower() in title.lower() or company.lower() in desc.lower():
                    if link:
                        if hist.normalize_headline(title) in SENT_KEYS:
                            continue  # already emailed in the last 10 days
                        CANDIDATES[link] = title
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
    # Record which stories actually made it into the email so we can remember
    # them and skip them on future runs. Match the hrefs back to candidate titles.
    for href in re.findall(r'href=["\']([^"\']+)["\']', body_html):
        title = CANDIDATES.get(href)
        if title:
            SENT_STORIES.append({"title": title, "url": href})

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
            max_tokens=8096,
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
    now = datetime.now()
    today = now.strftime("%B %d, %Y")
    today_iso = now.strftime("%Y-%m-%d")
    company_list = "\n".join(f"- {c}" for c in COMPANIES)

    print(f"\n{'='*60}")
    print(f"RK Group Daily Newsletter")
    print(f"Date      : {today}")
    print(f"Recipients: {recipient_str}")
    print(f"{'='*60}\n")

    # Load what we've already sent (last 10 days) so we don't repeat stories.
    history_entries, history_sha = hist.load_history()
    SENT_KEYS.update(hist.sent_keys(history_entries))
    already_covered = hist.recent_titles(history_entries, today_iso)
    print(f"  [history] {len(already_covered)} stories covered in the last 10 days.")

    exclusion_block = ""
    if already_covered:
        listed = "\n".join(f"- {t}" for t in already_covered)
        exclusion_block = f"""

ALREADY COVERED — DO NOT REPEAT THESE STORIES (sent in the last 10 days).
This includes the same story reported by a different outlet. If a search result
is about any of these, SKIP it and look for genuinely new developments only:
{listed}
"""

    system = (
        "You are an AI that produces a daily business intelligence newsletter for RK Group. "
        "You have tools to search news and send email. Be concise and factual. "
        "Only include genuinely NEW news from the past day. Never repeat a story that was "
        "already covered in a previous newsletter, even if a different outlet reported it. "
        "If no fresh news exists for a company, say 'No major news today.'"
    )

    prompt = f"""Today is {today}. Produce and send the RK Group Daily Intelligence Newsletter.

COMPANIES TO RESEARCH:
{company_list}

RK GROUP CONTEXT:
{RK_GROUP_CONTEXT}
{exclusion_block}
STEPS:
1. For each company, use search_news and fetch_rss_news to find news from the past day. The tools only return stories not already sent, but if a result clearly matches an ALREADY COVERED item above, skip it anyway.
2. Write a clean HTML newsletter email with:
   - Subject: "RK Intelligence | {today} | [1-line hook from top story]"
   - Header: "RK Group Intelligence" + date
   - Executive Summary: 3 most important things today
   - One section per company with 2-3 bullets: what happened + why it matters
   - Each bullet MUST end with a "Read more →" hyperlink using the article's URL, e.g.: <a href="URL" style="color:#0066cc;">Read more →</a>
   - Only include bullets where you have a real URL from the search results — no URL, no bullet
   - Skip companies with no news today (write "No major news today.")
   - Footer: "RK Group Intelligence | {today} | Confidential"
   - Clean white background, Arial font, mobile-friendly inline styles
3. Send the email to: {recipient_str}

Write the newsletter directly in the send_email call — do not return it as text."""

    result = run_agent(system, prompt)
    print("\nDone.")
    if result:
        print(result)

    # Remember the stories that actually went out, so tomorrow's run skips them.
    if SENT_STORIES:
        hist.save_history(history_entries, SENT_STORIES, history_sha, today_iso)
    else:
        print("  [history] no stories captured from the email — nothing to save.")


if __name__ == "__main__":
    run_newsletter()
