import os
from datetime import datetime
from crewai import Agent, Task, Crew, Process, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import List
from rk_newsletter.tools import search_news, fetch_rss_news, send_email
from rk_newsletter.config import COMPANIES


@CrewBase
class RkNewsletterCrew:
    """RK Group Daily Intelligence Newsletter Crew."""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def _llm(self) -> LLM:
        return LLM(
            model="groq/llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.3,
        )

    def _writer_llm(self) -> LLM:
        return LLM(
            model="anthropic/claude-haiku-4-5-20251001",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.4,
            max_tokens=8000,
        )

    def _date_str(self) -> str:
        return datetime.now().strftime("%B %d, %Y")

    def _company_list(self) -> str:
        return "\n".join(f"- {c}" for c in COMPANIES)

    def _recipient_str(self) -> str:
        env_val = os.getenv("NEWSLETTER_RECIPIENTS", "aryan@valuecart.in")
        return ", ".join(r.strip() for r in env_val.split(",") if r.strip())

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher"],  # type: ignore[index]
            tools=[search_news, fetch_rss_news],
            llm=self._llm(),
            verbose=True,
            max_iter=20,
        )

    @agent
    def writer(self) -> Agent:
        return Agent(
            config=self.agents_config["writer"],  # type: ignore[index]
            llm=self._writer_llm(),
            verbose=True,
        )

    @agent
    def sender(self) -> Agent:
        return Agent(
            config=self.agents_config["sender"],  # type: ignore[index]
            tools=[send_email],
            llm=self._writer_llm(),
            verbose=True,
        )

    @task
    def research_task(self) -> Task:
        date_str = self._date_str()
        company_list = self._company_list()
        return Task(
            description=f"""Search for the latest news (past 24 hours) on each of these companies and topics:

{company_list}

Today is {date_str}.

For each company/topic:
1. Use search_news to find recent Google News articles
2. Use fetch_rss_news to find articles from Inc42, YourStory, Entrackr, and Mint
3. Combine the best 2-4 stories per company/topic

STRICT RULES — no exceptions:
- Only report stories you actually found via the tools. Never invent or assume news.
- Only include URLs that were returned by the tools. Never generate or guess a URL.
- If no news found for a company/topic, write exactly: "No news found today."

Return a structured research report, one section per company/topic:
Format per bullet: "- [headline/what happened] | SOURCE: [publication name] | URL: [exact url from tool]"
""",
            expected_output="Structured research report: one section per company/topic, 2-4 bullets each with exact source name and URL from the tools.",
            agent=self.researcher(),
        )

    @task
    def write_task(self) -> Task:
        date_str = self._date_str()
        company_list = self._company_list()
        return Task(
            description=f"""Using the research report, write the RK Group Intelligence Newsletter for {date_str}.

You MUST include a section for EVERY company/topic listed below, in this exact order:
{company_list}

Even if a company has no news, include its section with "No news today." — do NOT skip any company.

Return a JSON object with exactly two keys:
1. "subject": "RK Intelligence | {date_str} | [1-line hook from top story]"
2. "html": complete HTML email body

Use this exact HTML structure and styling:

<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:20px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
        <!-- HEADER -->
        <tr><td style="background:#1a1a2e;padding:30px 40px;text-align:center">
          <h1 style="color:#ffffff;margin:0;font-size:24px;letter-spacing:2px">RK GROUP INTELLIGENCE</h1>
          <p style="color:#a0a0c0;margin:8px 0 0;font-size:14px">{date_str}</p>
        </td></tr>
        <!-- EXECUTIVE SUMMARY -->
        <tr><td style="background:#f8f9ff;padding:24px 40px;border-left:4px solid #4a90d9">
          <h2 style="color:#1a1a2e;margin:0 0 12px;font-size:13px;letter-spacing:1px;text-transform:uppercase">Executive Summary</h2>
          <p style="color:#333;margin:0;font-size:15px;line-height:1.7">[3 sentence summary of the 3 most important things today]</p>
        </td></tr>
        <!-- COMPANY SECTIONS (repeat for each company) -->
        <tr><td style="padding:24px 40px;border-bottom:1px solid #eee">
          <h2 style="color:#1a1a2e;margin:0 0 12px;font-size:16px">[COMPANY NAME]</h2>
          <ul style="margin:0;padding-left:20px;color:#444;font-size:14px;line-height:1.8">
            <li><strong>[crisp headline — max 15 words]</strong> <a href="[EXACT URL from research report]" style="color:#4a90d9;text-decoration:none;font-size:12px">Read more →</a></li>
            <li><strong>[crisp headline — max 15 words]</strong> <a href="[EXACT URL from research report]" style="color:#4a90d9;text-decoration:none;font-size:12px">Read more →</a></li>
          </ul>
        </td></tr>
        <!-- FOOTER -->
        <tr><td style="background:#1a1a2e;padding:20px 40px;text-align:center">
          <p style="color:#a0a0c0;margin:0;font-size:12px">RK Group Intelligence | Compiled {date_str} | Confidential</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>

STRICT RULES — no exceptions:
- Include ALL companies/topics listed above. Do NOT skip any, even if there is no news.
- Use ONLY the news and URLs from the research report above. Do not add, invent, or assume any information.
- Every "Read more →" link must use the EXACT URL from the research report. Never generate a URL yourself.
- If a company has no news in the research report, write "No news today." — do not fill in placeholder content.
- Bullets are factual headlines only — no commentary on what it means, no analysis, no opinion.
- Max 15 words per bullet.

Return ONLY the JSON object, no markdown fences.""",
            expected_output='A JSON object with "subject" and "html" keys containing a polished HTML newsletter.',
            agent=self.writer(),
            context=[self.research_task()],
        )

    @task
    def send_task(self) -> Task:
        recipient_str = self._recipient_str()
        return Task(
            description=f"""Send the newsletter to: {recipient_str}

Parse the JSON from the previous task to get the subject and HTML body.
Call send_email with:
- to: "{recipient_str}"
- subject: the subject from the JSON
- body_html: the html from the JSON

Report whether the email was sent successfully.""",
            expected_output="Confirmation that the email was sent successfully.",
            agent=self.sender(),
            context=[self.write_task()],
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
