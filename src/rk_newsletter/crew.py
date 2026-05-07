import os
from datetime import datetime
from crewai import Agent, Task, Crew, Process, LLM
from .tools import search_news, send_email
from .config import COMPANIES, RK_GROUP_CONTEXT


def build_crew(recipients: list[str]) -> Crew:
    week_str = datetime.now().strftime("%B %d, %Y")
    company_list = "\n".join(f"- {c}" for c in COMPANIES)
    recipient_str = ", ".join(recipients)

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.3,
    )

    researcher = Agent(
        role="Market Intelligence Researcher",
        goal="Find the most relevant business news from the past 7 days for each company in the RK Group watchlist.",
        backstory=(
            "You are a sharp market intelligence analyst covering Indian e-commerce, retail, "
            "and brand distribution. You know what moves the needle for a brand distributor "
            "and marketplace operator. You search fast and filter ruthlessly."
        ),
        tools=[search_news],
        llm=llm,
        verbose=True,
        max_iter=15,
    )

    writer = Agent(
        role="Executive Newsletter Editor",
        goal="Turn raw research into a crisp, well-formatted HTML newsletter a founder can read in 90 seconds.",
        backstory=(
            "You write for founders and senior leaders who have no patience for fluff. "
            "Every word earns its place. You produce clean HTML emails with maximum signal."
        ),
        llm=llm,
        verbose=True,
    )

    sender = Agent(
        role="Email Delivery Agent",
        goal="Send the newsletter HTML to all recipients using the send_email tool.",
        backstory=(
            "You are responsible for reliable email delivery. "
            "You call the send_email tool with the exact subject and HTML body provided."
        ),
        tools=[send_email],
        llm=llm,
        verbose=True,
    )

    research_task = Task(
        description=f"""Search for the latest news (past 7 days) on each of these companies:

{company_list}

RK GROUP CONTEXT — focus on what matters:
{RK_GROUP_CONTEXT}

For each company run a search and collect the top stories. Today is {week_str}.

Return a structured research report: one section per company, 2-4 bullet points each.
Format: "- [what happened] — [why it matters to RK Group]"
If no significant news, write "No major news this week." for that company.""",
        expected_output="Structured research report with one section per company and 2-4 bullet points each.",
        agent=researcher,
    )

    write_task = Task(
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
        agent=writer,
        context=[research_task],
    )

    send_task = Task(
        description=f"""Send the newsletter to: {recipient_str}

Parse the JSON from the previous task to get the subject and HTML body.
Call send_email with:
- to: "{recipient_str}"
- subject: the subject from the JSON
- body_html: the html from the JSON

Report whether the email was sent successfully.""",
        expected_output="Confirmation that the email was sent successfully.",
        agent=sender,
        context=[write_task],
    )

    return Crew(
        agents=[researcher, writer, sender],
        tasks=[research_task, write_task, send_task],
        process=Process.sequential,
        verbose=True,
    )
