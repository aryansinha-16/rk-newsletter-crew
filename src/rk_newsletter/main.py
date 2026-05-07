import sys
import os
from dotenv import load_dotenv
from rk_newsletter.crew import RkNewsletterCrew

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    print("\nRK Group Newsletter (CrewAI+)")
    RkNewsletterCrew().crew().kickoff()


if __name__ == "__main__":
    run()
