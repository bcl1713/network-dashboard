"""EVE JSON normalization.

Suricata's EVE format is fairly stable but not all fields are guaranteed.
We extract the subset the rest of the engine cares about and stash the original
payload alongside it so audit / why-hidden can show the raw event later.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class NormalizedEvent:
    event_id: str
    timestamp: datetime
    event_type: str
    src_ip: str | None
    src_port: int | None
    dest_ip: str | None
    dest_port: int | None
    proto: str | None
    sid: int | None
    generator_id: int | None
    signature: str | None
    severity: int | None
    host: str | None
    geoip_country: str | None
    geoip_city: str | None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_loki_labels(self, action: str) -> dict[str, str]:
        """Bounded label set for Loki streams. Never include dest_ip."""
        return {
            "job": "suricata",
            "host": self.host or self.src_ip or "unknown",
            "sid": str(self.sid) if self.sid is not None else "0",
            "severity": str(self.severity) if self.severity is not None else "0",
            "action": action,
        }


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _stable_event_id(payload: dict[str, Any]) -> str:
    """Use Suricata's flow_id when present so retries dedupe naturally."""
    flow_id = payload.get("flow_id")
    ts = payload.get("timestamp", "")
    if flow_id is not None and ts:
        digest = hashlib.sha256(f"{flow_id}:{ts}".encode()).hexdigest()
        return digest[:32]
    return uuid.uuid4().hex


def normalize(payload: dict[str, Any]) -> NormalizedEvent:
    """Build a NormalizedEvent from a raw EVE JSON dict.

    Missing fields are tolerated; downstream callers handle Nones explicitly.
    """
    alert = payload.get("alert") or {}
    geoip = payload.get("geoip") or payload.get("alert", {}).get("geoip") or {}

    return NormalizedEvent(
        event_id=_stable_event_id(payload),
        timestamp=_parse_ts(payload.get("timestamp")),
        event_type=str(payload.get("event_type") or "unknown"),
        src_ip=payload.get("src_ip"),
        src_port=_coerce_int(payload.get("src_port")),
        dest_ip=payload.get("dest_ip"),
        dest_port=_coerce_int(payload.get("dest_port")),
        proto=payload.get("proto"),
        sid=_coerce_int(alert.get("signature_id")),
        generator_id=_coerce_int(alert.get("gid")),
        signature=alert.get("signature"),
        severity=_coerce_int(alert.get("severity")),
        host=payload.get("host") or payload.get("hostname"),
        geoip_country=geoip.get("country_name") or geoip.get("country"),
        geoip_city=geoip.get("city_name") or geoip.get("city"),
        raw=payload,
    )
