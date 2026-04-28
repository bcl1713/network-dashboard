"""Idempotent seed of common filter rules.

Run inside the engine container:

    python -m scripts.seed_filters

Re-running is safe: existing rules with the same `name` are left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import init_engine, session_scope  # noqa: E402
from app.models import Filter  # noqa: E402

SEEDS: list[dict] = [
    {
        "name": "Telegram bot noise (example)",
        "description": "Outbound Telegram bot API; tag-only example. Disable until you confirm host.",
        "enabled": False,
        "action": "tag",
        "sid": 2027865,
        "notes": "Replace source_host with the actual bot's IP before enabling.",
    },
    {
        "name": "Public DNS from IoT subnet (example)",
        "description": "DNS queries from IoT VLAN to public resolvers; tag for visibility.",
        "enabled": False,
        "action": "tag",
        "source_subnet": "10.10.60.0/24",
        "sid": 2010935,
        "notes": "Subnet-wide tag, enable after confirming subnet matches your environment.",
    },
]


def main() -> int:
    settings = get_settings()
    init_engine(settings.db_path)
    inserted = 0
    skipped = 0
    with session_scope() as session:
        for spec in SEEDS:
            existing = session.query(Filter).filter(Filter.name == spec["name"]).one_or_none()
            if existing is not None:
                skipped += 1
                continue
            session.add(Filter(**spec))
            inserted += 1
        session.commit()
    print(f"seed: inserted={inserted} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
