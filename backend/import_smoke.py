#!/usr/bin/env python3
"""Import every backend module and report real failures.

compileall only checks syntax. This walks app/, imports each module, and
prints the modules that raise. Run from backend/ with the venv python.

Env vars are set to inert placeholders: nothing here opens a network
connection or sends mail.
"""
import importlib
import os
import pathlib
import sys
import traceback

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "smoke-test-secret-not-real")
os.environ.setdefault("CHAMPGRAPH_URL", "http://localhost:8080")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("TESTING", "true")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

APP = pathlib.Path("app")
failures: list[tuple[str, str]] = []
count = 0

for path in sorted(APP.rglob("*.py")):
    rel = path.relative_to(APP).with_suffix("")
    module = "app." + ".".join(rel.parts)
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    if not module:
        continue
    count += 1
    try:
        importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic tool
        tb = traceback.format_exc().strip().splitlines()
        failures.append((module, f"{type(exc).__name__}: {exc}"))
        if "-v" in sys.argv:
            print("\n".join(tb[-6:]), file=sys.stderr)

print(f"modules attempted: {count}")
print(f"import failures:   {len(failures)}")
for module, err in failures:
    print(f"  FAIL {module}: {err}")

sys.exit(1 if failures else 0)