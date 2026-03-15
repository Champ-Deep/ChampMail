#!/usr/bin/env python3
"""
Startup wrapper that catches silent import crashes.

Problem: When uvicorn imports app.main via CLI (uvicorn app.main:app),
any exception during module import is swallowed — no traceback, no logs.
This wrapper imports app.main in a try/except block so failures are visible
in Railway deployment logs.

NOTE: Uses print(flush=True) instead of logging — Railway deploy logs
only reliably capture stdout, not stderr from Python's logging module.
"""

import os
import sys

print("=== Importing app.main ===", flush=True)
try:
    from app.main import app  # noqa: F401
    print("=== Import OK ===", flush=True)
except Exception as e:
    print(f"=== IMPORT FAILED: {type(e).__name__}: {e} ===", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

import uvicorn

port = int(os.environ.get("PORT", "8000"))
print(f"=== Starting uvicorn on 0.0.0.0:{port} ===", flush=True)
uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
