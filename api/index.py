"""Vercel entry point: the ANT-OS API as one Python serverless function.

The repository's packages are put on the import path directly, and Vercel's own
variable names (DATABASE_URL from the Neon integration, CRON_SECRET for scheduled
calls) are mapped onto the ANTOS_* settings.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for src in ("packages/antos-core/src", "services/api/src"):
    sys.path.insert(0, str(ROOT / src))

os.environ.setdefault("ANTOS_PROFILE_DIR", str(ROOT / "profiles" / "africa"))
os.environ.setdefault("ANTOS_SERVERLESS", "true")
os.environ.setdefault("ANTOS_TRUST_FORWARDED_FOR", "true")
# Prefer the direct (unpooled) connection: asyncpg's prepared statements do not
# survive a transaction-mode pooler, and a demo needs few connections.
for target, sources in (("ANTOS_DATABASE_URL", ("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING",
                                                "DATABASE_URL", "POSTGRES_URL")),
                        ("ANTOS_CRON_SECRET", ("CRON_SECRET",))):
    if target not in os.environ:
        for name in sources:
            if os.environ.get(name):
                os.environ[target] = os.environ[name]
                break

from antos_api.app import create_app  # noqa: E402

app = create_app()
