from datetime import datetime, timedelta, timezone

from app.classifier import classify, explain
from app.eve import NormalizedEvent
from app.models import Filter


def _ev(**kw) -> NormalizedEvent:
    base = dict(
        event_id="abc",
        timestamp=datetime.now(tz=timezone.utc),
        event_type="alert",
        src_ip="10.10.50.42",
        src_port=51514,
        dest_ip="149.154.167.41",
        dest_port=443,
        proto="TCP",
        sid=2027865,
        generator_id=1,
        signature="ET POLICY Telegram Outbound Bot API",
        severity=2,
        host="opnsense",
        geoip_country=None,
        geoip_latitude=None,
        geoip_longitude=None,
        raw={},
    )
    base.update(kw)
    return NormalizedEvent(**base)


def _rule(**kw) -> Filter:
    rule = Filter()
    rule.id = kw.pop("id", 1)
    rule.name = kw.pop("name", "test")
    rule.enabled = 1
    rule.retired = 0
    rule.action = kw.pop("action", "tag")
    rule.match_mode = "exact"
    rule.hit_count = 0
    for k, v in kw.items():
        setattr(rule, k, v)
    return rule


def test_no_rules_returns_passthrough():
    d = classify(_ev(), [])
    assert d.action == "passthrough"
    assert d.filter_id is None


def test_host_plus_sid_match_returns_action():
    rule = _rule(source_host="10.10.50.42", sid=2027865, action="hide")
    d = classify(_ev(), [rule])
    assert d.action == "hide"
    assert d.filter_id == 1
    assert d.matched_fields["sid"] == 2027865


def test_host_mismatch_does_not_match():
    rule = _rule(source_host="10.10.50.99", sid=2027865, action="hide")
    d = classify(_ev(), [rule])
    assert d.action == "passthrough"


def test_subnet_matches():
    rule = _rule(source_subnet="10.10.50.0/24", sid=2027865, action="tag")
    d = classify(_ev(), [rule])
    assert d.action == "tag"
    assert d.matched_fields["src"]["subnet"] == "10.10.50.0/24"


def test_more_specific_rule_wins_over_sid_only():
    # SID-only requires opt-in; without it, an SID-only rule must be skipped.
    sid_only = _rule(id=1, sid=2027865, action="hide")
    host_specific = _rule(id=2, source_host="10.10.50.42", sid=2027865, action="tag")
    d = classify(_ev(), [sid_only, host_specific])
    assert d.action == "tag"
    assert d.filter_id == 2


def test_sid_only_only_when_explicitly_allowed():
    rule = _rule(sid=2027865, action="hide")
    d_off = classify(_ev(), [rule], allow_sid_only=False)
    d_on = classify(_ev(), [rule], allow_sid_only=True)
    assert d_off.action == "passthrough"
    assert d_on.action == "hide"


def test_dest_port_and_proto_must_match():
    # Right host+sid but wrong port -> miss.
    miss = _rule(source_host="10.10.50.42", sid=2027865, destination_port=80, action="hide")
    d = classify(_ev(), [miss])
    assert d.action == "passthrough"

    # Right port+proto -> hit.
    hit = _rule(
        source_host="10.10.50.42", sid=2027865, destination_port=443, protocol="tcp", action="hide"
    )
    d = classify(_ev(), [hit])
    assert d.action == "hide"


def test_message_match_modes():
    rule = _rule(
        source_host="10.10.50.42",
        sid=2027865,
        message_match="Telegram",
        match_mode="contains",
        action="tag",
    )
    d = classify(_ev(), [rule])
    assert d.action == "tag"

    rule.match_mode = "regex"
    rule.message_match = r"^ET POLICY Telegram.*Bot"
    d = classify(_ev(), [rule])
    assert d.action == "tag"

    rule.match_mode = "exact"
    rule.message_match = "Different signature"
    d = classify(_ev(), [rule])
    assert d.action == "passthrough"


def test_retired_rules_skipped():
    rule = _rule(source_host="10.10.50.42", sid=2027865, action="hide")
    rule.retired = 1
    d = classify(_ev(), [rule])
    assert d.action == "passthrough"


def test_disabled_rules_skipped():
    rule = _rule(source_host="10.10.50.42", sid=2027865, action="hide")
    rule.enabled = 0
    d = classify(_ev(), [rule])
    assert d.action == "passthrough"


def test_expired_rules_skipped():
    rule = _rule(source_host="10.10.50.42", sid=2027865, action="hide")
    rule.expires_at = datetime.now(tz=timezone.utc) - timedelta(days=1)
    d = classify(_ev(), [rule])
    assert d.action == "passthrough"


def test_allow_overrides_to_passthrough():
    allow_rule = _rule(id=1, source_host="10.10.50.42", sid=2027865, action="allow")
    hide_rule = _rule(id=2, source_subnet="10.10.50.0/24", sid=2027865, action="hide")
    d = classify(_ev(), [allow_rule, hide_rule])
    # Allow is more specific (host > subnet) so it wins and short-circuits.
    assert d.action == "passthrough"
    assert d.filter_id == 1


def test_explain_returns_chain():
    miss = _rule(id=1, source_host="10.10.50.99", sid=2027865, action="hide")
    hit = _rule(id=2, source_host="10.10.50.42", sid=2027865, action="tag")
    d, chain = explain(_ev(), [miss, hit])
    assert d.action == "tag"
    # Two rules considered; both have host+sid so both appear in the chain
    # before the matcher short-circuits on the first hit.
    matched_ids = [s.filter_id for s in chain if s.matched]
    assert matched_ids == [2]
