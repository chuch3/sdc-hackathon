"""Container startup: migrate, then serve. Seeding remains an explicit command."""

import os
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    if os.getenv("AUTO_SEED_DEMO", "").lower() in {"1", "true", "yes"}:
        seeded = subprocess.run([sys.executable, "-m", "scripts.seed"], check=False)
        if seeded.returncode:
            print("Demo seed skipped; the database already contains data.")
    port = os.getenv("PORT", "8000")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port],
        check=True,
    )
