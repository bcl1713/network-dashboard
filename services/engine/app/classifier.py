"""Deterministic alert classifier.

Evaluation order (most-specific → least-specific). First match wins:

  1. host + SID + destination + port/proto
  2. host + SID + destination
  3. host + SID
  4. SID-only fallback (only when allow_sid_only=True)
  5. message text match (exact/contains/regex)

`allow` short-circuits to passthrough (overrides any later tag/hide).
Retired or expired filters are skipped.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .eve import NormalizedEvent
from .models import Filter

DecisionAction = str  # "tag" | "hide" | "allow" | "passthrough"


@dataclass(slots=True)
class Decision:
    action: DecisionAction
    filter_id: int | None
    matched_fields: dict


@dataclass(slots=True)
class ChainStep:
    filter_id: int
    name: str
    action: str
    matched: bool
    matched_fields: dict


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_active(rule: Filter, now: datetime | None = None) -> bool:
    if not rule.enabled or rule.retired:
        return False
    if rule.expires_at is not None:
        now = now or _now_utc()
        ea = rule.expires_at if rule.expires_at.tzinfo else rule.expires_at.replace(tzinfo=timezone.utc)
        if ea <= now:
            return False
    return True


def _ip_in(value: str | None, host: str | None, subnet: str | None) -> tuple[bool, dict]:
    """Return (matched, matched_fields). Returns matched=True if no constraint set."""
    if host is None and subnet is None:
        return True, {}
    if value is None:
        return False, {}
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False, {}
    if host is not None:
        try:
            if addr == ipaddress.ip_address(host):
                return True, {"host": host}
        except ValueError:
            return False, {}
        return False, {}
    if subnet is not None:
        try:
            net = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            return False, {}
        if addr in net:
            return True, {"subnet": subnet}
    return False, {}


def _message_matches(event: NormalizedEvent, rule: Filter) -> tuple[bool, dict]:
    if not rule.message_match:
        return True, {}
    sig = event.signature or ""
    needle = rule.message_match
    mode = rule.match_mode or "exact"
    try:
        if mode == "exact":
            ok = sig == needle
        elif mode == "contains":
            ok = needle.lower() in sig.lower()
        elif mode == "regex":
            ok = re.search(needle, sig) is not None
        else:
            ok = False
    except re.error:
        ok = False
    return ok, ({"message": needle, "mode": mode} if ok else {})


def _matches(event: NormalizedEvent, rule: Filter) -> tuple[bool, dict]:
    """Return (True, matched_fields) if every non-null criterion matches."""
    matched_fields: dict = {}

    src_ok, src_match = _ip_in(event.src_ip, rule.source_host, rule.source_subnet)
    if not src_ok:
        return False, {}
    if src_match:
        matched_fields["src"] = src_match

    dest_ok, dest_match = _ip_in(event.dest_ip, rule.destination, rule.destination_subnet)
    if not dest_ok:
        return False, {}
    if dest_match:
        matched_fields["dest"] = dest_match

    if rule.sid is not None:
        if event.sid != rule.sid:
            return False, {}
        matched_fields["sid"] = rule.sid

    if rule.generator_id is not None:
        if event.generator_id != rule.generator_id:
            return False, {}
        matched_fields["gid"] = rule.generator_id

    if rule.destination_port is not None:
        if event.dest_port != rule.destination_port:
            return False, {}
        matched_fields["dest_port"] = rule.destination_port

    if rule.protocol is not None:
        if (event.proto or "").lower() != rule.protocol.lower():
            return False, {}
        matched_fields["protocol"] = rule.protocol

    msg_ok, msg_match = _message_matches(event, rule)
    if not msg_ok:
        return False, {}
    matched_fields.update(msg_match)

    return True, matched_fields


def _specificity(rule: Filter) -> int:
    """Higher is more specific. Used to order tiered evaluation."""
    score = 0
    if rule.source_host is not None:
        score += 8
    elif rule.source_subnet is not None:
        score += 4
    if rule.sid is not None:
        score += 4
    if rule.generator_id is not None:
        score += 1
    if rule.destination is not None:
        score += 4
    elif rule.destination_subnet is not None:
        score += 2
    if rule.destination_port is not None:
        score += 2
    if rule.protocol is not None:
        score += 1
    if rule.message_match:
        score += 2
    return score


def order_for_evaluation(rules: Iterable[Filter]) -> list[Filter]:
    """Return rules sorted most-specific first."""
    return sorted(rules, key=lambda r: (-_specificity(r), r.id))


def classify(
    event: NormalizedEvent,
    rules: Iterable[Filter],
    *,
    allow_sid_only: bool = False,
) -> Decision:
    """Walk the active rules and return the first matching action."""
    now = _now_utc()
    for rule in order_for_evaluation(rules):
        if not _is_active(rule, now=now):
            continue

        # Guard against accidentally over-broad SID-only filters.
        if (
            not allow_sid_only
            and rule.source_host is None
            and rule.source_subnet is None
            and rule.destination is None
            and rule.destination_subnet is None
            and rule.destination_port is None
            and rule.protocol is None
            and not rule.message_match
            and rule.sid is not None
        ):
            continue

        ok, fields = _matches(event, rule)
        if not ok:
            continue
        action = rule.action if rule.action != "allow" else "passthrough"
        return Decision(action=action, filter_id=rule.id, matched_fields=fields)

    return Decision(action="passthrough", filter_id=None, matched_fields={})


def explain(
    event: NormalizedEvent,
    rules: Iterable[Filter],
    *,
    allow_sid_only: bool = False,
) -> tuple[Decision, list[ChainStep]]:
    """Like classify(), but returns every rule considered for why-hidden."""
    chain: list[ChainStep] = []
    decided: Decision | None = None
    now = _now_utc()
    for rule in order_for_evaluation(rules):
        if not _is_active(rule, now=now):
            continue
        if (
            not allow_sid_only
            and rule.source_host is None
            and rule.source_subnet is None
            and rule.destination is None
            and rule.destination_subnet is None
            and rule.destination_port is None
            and rule.protocol is None
            and not rule.message_match
            and rule.sid is not None
        ):
            continue
        ok, fields = _matches(event, rule)
        chain.append(
            ChainStep(
                filter_id=rule.id,
                name=rule.name,
                action=rule.action,
                matched=ok,
                matched_fields=fields,
            )
        )
        if ok and decided is None:
            action = rule.action if rule.action != "allow" else "passthrough"
            decided = Decision(action=action, filter_id=rule.id, matched_fields=fields)
            break

    if decided is None:
        decided = Decision(action="passthrough", filter_id=None, matched_fields={})
    return decided, chain
