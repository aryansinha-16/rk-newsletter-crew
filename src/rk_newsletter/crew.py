import os
from datetime import datetime
from crewai import Agent, Task, Crew, Process, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import List
from rk_newsletter.tools import search_news, send_email
from rk_newsletter.config import COMPANIES, RK_GROUP_CONTEXT


@CrewBase
class RkNewsletterCrew:
    """RK Group Weekly Intelligence Newsletter Crew."""

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
        )

    def _week_str(self) -> str:
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
            tools=[search_news],
            llm=self._llm(),
            verbose=True,
            max_iter=15,
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
            llm=self._llm(),
            verbose=True,
        )

    @task
    def research_task(self) -> Task:
        week_str = self._week_str()
        company_list = self._company_list()
        return Task(
            description=f"""Search for the latest news (past 7 days) on each of these companies:

{company_list}

RK GROUP CONTEXT — focus on what matters:
{RK_GROUP_CONTEXT}

For each company run a search and collect the top stories. Today is {week_str}.

Return a structured research report: one section per company, 2-4 bullet points each.
Format: "- [what happened] — [why it matters to RK Group] | URL: [source url]"
Always include the source URL for each point. If no significant news, write "No major news this week." for that company.""",
            expected_output="Structured research report with one section per company, 2-4 bullet points each, each with a source URL.",
            agent=self.researcher(),
        )

    @task
    def write_task(self) -> Task:
        week_str = self._week_str()
        return Task(
            description=f"""Using the research report, write the RK Group Intelligence Newsletter for the week of {week_str}.

Return a JSON object with exactly two keys:
1. "subject": "RK Intelligence | Week of {week_str} | [1-line hook from top story]"
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
          <p style="color:#a0a0c0;margin:8px 0 0;font-size:14px">Week of {week_str}</p>
        </td></tr>
        <!-- EXECUTIVE SUMMARY -->
        <tr><td style="background:#f8f9ff;padding:24px 40px;border-left:4px solid #4a90d9">
          <h2 style="color:#1a1a2e;margin:0 0 12px;font-size:13px;letter-spacing:1px;text-transform:uppercase">Executive Summary</h2>
          <p style="color:#333;margin:0;font-size:15px;line-height:1.7">[3 sentence summary of the 3 most important things this week]</p>
        </td></tr>
        <!-- COMPANY SECTIONS (repeat for each company) -->
        <tr><td style="padding:24px 40px;border-bottom:1px solid #eee">
          <h2 style="color:#1a1a2e;margin:0 0 12px;font-size:16px">[COMPANY NAME]</h2>
          <ul style="margin:0;padding-left:20px;color:#444;font-size:14px;line-height:1.8">
            <li><strong>[what happened]</strong> — [why it matters to RK Group in one sentence] <a href="[source URL]" style="color:#4a90d9;text-decoration:none;font-size:12px">Read more →</a></li>
            <li><strong>[what happened]</strong> — [why it matters to RK Group in one sentence] <a href="[source URL]" style="color:#4a90d9;text-decoration:none;font-size:12px">Read more →</a></li>
          </ul>
        </td></tr>
        <!-- FOOTER -->
        <tr><td style="background:#1a1a2e;padding:20px 40px;text-align:center">
          <p style="color:#a0a0c0;margin:0;font-size:12px">RK Group Intelligence | Compiled {week_str} | Confidential</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>

Fill in all 7 company sections with real content from the research. Make the executive summary punchy and specific.
TONE: Crisp and direct. Max 15 words per bullet. No filler. Write like a founder who reads fast.
Each bullet MUST end with a "Read more" link using the source URL from the research report.
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
