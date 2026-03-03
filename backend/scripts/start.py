#!/usr/bin/env python3
"""
Startup wrapper that catches silent import crashes.

Problem: When uvicorn imports app.main via CLI (uvicorn app.main:app),
any exception during module import is swallowed — no traceback, no logs.
This wrapper imports app.main in a try/except block so failures are visible
in Railway deployment logs.
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
logger = logging.getLogger("startup")

logger.info("=== Importing app.main ===")
try:
    from app.main import app  # noqa: F401
    logger.info("=== Import OK ===")
except Exception as e:
    logger.error("=== IMPORT FAILED ===")
    logger.error("%s: %s", type(e).__name__, e)
    import traceback
    traceback.print_exc()
    sys.exit(1)

import uvicorn

port = int(os.environ.get("PORT", "8000"))
logger.info("=== Starting uvicorn on port %d ===", port)
uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
