"""Create the synthetic demo accounts and their data in the configured database.

Run from backend/:   .venv\\Scripts\\python.exe scripts\\seed_demo.py
Safe to run more than once. Everything it creates is invented and labelled "Demo"; nothing claims to come
from a real university or from Microsoft Teams. Accounts are listed in docs/DEMO.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.database import SessionLocal, engine  # noqa: E402
from app.demo_seed import seed  # noqa: E402
from app.migrate import upgrade_database  # noqa: E402


if __name__ == "__main__":
    upgrade_database(engine)
    with SessionLocal() as db:
        print("Demo data created." if seed(db) else "Demo accounts already exist; nothing changed.")
