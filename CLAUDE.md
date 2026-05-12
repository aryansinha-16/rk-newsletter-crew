# RK Newsletter — Project Context

## What this is
Daily business intelligence newsletter for RK Group. Runs as a Railway worker.
Researches news for a watchlist of Indian companies and emails an HTML newsletter via SendGrid.

## Stack
- **Python 3.12** (no CrewAI — replaced with plain Anthropic API tool-use loop)
- **Anthropic API** — claude-haiku-4-5-20251001, max_tokens=8096
- **Serper API** — Google News search, `tbs=qdr:2d` (past 2 days only)
- **RSS feeds** — Inc42, YourStory, Entrackr, Mint (filtered to past 2 days via pubDate)
- **SendGrid** — via Railway MCP server at `https://valuecart-email-mcp-production.up.railway.app/mcp/valuecart2026`
- **Railway** — deployed via Dockerfile, cron schedule triggers daily

## Key files
- `main.py` — entire pipeline: tools, agentic loop, scheduler entry point
- `Dockerfile` — `python:3.12-slim`, installs `requirements.txt`, runs `python main.py`
- `railway.json` — builder: DOCKERFILE
- `requirements.txt` — anthropic, requests, python-dotenv

## Companies watched
Amazon India, Flipkart, Myntra, PharmEasy, Nike India, Blinkit, Aditya Birla Group, Cars24, Scapia, Smytten, India China Relations

## Railway deployment
- Repo: `aryansinha-16/rk-newsletter-crew` (master branch)
- Service: `rk-newsletter-crew` on `grand-elegance` project
- Env vars needed: `ANTHROPIC_API_KEY`, `SERPER_API_KEY`, `NEWSLETTER_RECIPIENTS`
- Cron: set in Railway Settings → Deploy → Cron Schedule (e.g. `30 2 * * *` = 8 AM IST)
- Script runs and exits (no infinite loop) — Railway cron handles scheduling

## Known issues fixed
- Old articles (10 months old) coming through RSS → fixed with 2-day pubDate filter
- CrewAI was unreliable → replaced entirely with direct Anthropic API
- nixpacks couldn't find pip → switched to Dockerfile build
- max_tokens=4096 too small to write full HTML + call send_email → bumped to 8096
- Each newsletter bullet must include a real `Read more →` hyperlink (URL from search results)

## How to run locally
```bash
cd C:\Users\syste\CrewAI\rk_newsletter
.venv\Scripts\activate
python main.py
```

## Env vars (in .env, do not commit)
```
ANTHROPIC_API_KEY=...
SERPER_API_KEY=...
NEWSLETTER_RECIPIENTS=sonal@valuecart.in, aryan@valuecart.in, shrinivas@jennifer-in.com
```
