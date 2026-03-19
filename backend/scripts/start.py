#!/usr/bin/env python3
"""
Single entry point for ChampMail backend on Railway.

Runs migrations as a subprocess (isolated, with timeout), then imports
and starts the FastAPI app via uvicorn — all in one process.

Previous approach chained two processes via shell (migrate.py; start.py)
but Railway's container runtime didn't reliably launch the second process.
This single-process approach eliminates that failure mode entirely.
"""

import os
import subprocess
import sys

print("=== ChampMail Backend Starting ===", flush=True)

# Step 1: Run migrations as subprocess (isolated — avoids module-level side effects)
print("=== Running migrations ===", flush=True)
try:
    result = subprocess.run(
        [sys.executable, "scripts/migrate.py"],
        timeout=60,
    )
    print(f"=== Migrations finished (exit code {result.returncode}) ===", flush=True)
except subprocess.TimeoutExpired:
    print("!!! Migrations timed out after 60s — starting server anyway", flush=True)
except Exception as e:
    print(f"!!! Migration error: {e} — starting server anyway", flush=True)

# Step 2: Import the FastAPI app
print("=== Importing app.main ===", flush=True)
try:
    from app.main import app  # noqa: F401
    print("=== Import OK ===", flush=True)
except Exception as e:
    print(f"=== IMPORT FAILED: {type(e).__name__}: {e} ===", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Start uvicorn
import uvicorn

port = int(os.environ.get("PORT", "8000"))
print(f"=== Starting uvicorn on 0.0.0.0:{port} ===", flush=True)
uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
