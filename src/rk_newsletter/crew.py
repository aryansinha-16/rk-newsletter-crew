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
            llm=self._llm(),
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
Format: "- [what happened] — [why it matters to RK Group]"
If no significant news, write "No major news this week." for that company.""",
            expected_output="Structured research report with one section per company and 2-4 bullet points each.",
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

HTML REQUIREMENTS:
- White background (#ffffff), dark text (#1a1a1a), Arial sans-serif
- Header: "RK Group Intelligence" bold, date below
- EXECUTIVE SUMMARY: 3 sentences, the 3 most important things this week
- One section per company, 2-3 bullets: what happened + why it matters to RK Group
- Footer: "RK Group Intelligence | Compiled {week_str} | Confidential"
- Simple inline styles, mobile-friendly

TONE: Direct. No filler. Write like a founder.
Return ONLY the JSON, no markdown fences.""",
            expected_output='A JSON object with "subject" and "html" keys.',
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
