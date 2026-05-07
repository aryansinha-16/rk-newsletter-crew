import sys
import os
from dotenv import load_dotenv
from rk_newsletter.crew import build_crew

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    recipients_env = os.getenv("NEWSLETTER_RECIPIENTS", "aryan@valuecart.in")
    recipients = [r.strip() for r in recipients_env.split(",") if r.strip()]

    print(f"\nRK Group Newsletter (CrewAI+)")
    print(f"Recipients: {', '.join(recipients)}\n")

    crew = build_crew(recipients)
    crew.kickoff()
