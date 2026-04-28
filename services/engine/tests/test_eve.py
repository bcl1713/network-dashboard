from datetime import datetime, timezone

from app.eve import normalize


def test_normalize_extracts_alert_fields(basic_event):
    e = normalize(basic_event)
    assert e.event_type == "alert"
    assert e.src_ip == "10.10.50.42"
    assert e.dest_ip == "149.154.167.41"
    assert e.dest_port == 443
    assert e.proto == "TCP"
    assert e.sid == 2027865
    assert e.generator_id == 1
    assert e.severity == 2
    assert e.signature == "ET POLICY Telegram Outbound Bot API"
    assert e.host == "opnsense.local"
    assert e.geoip_country == "United Kingdom"
    assert e.geoip_city == "London"
    assert e.event_id  # deterministic, non-empty


def test_normalize_event_id_is_stable_for_same_flow(basic_event):
    a = normalize(basic_event)
    b = normalize(basic_event)
    assert a.event_id == b.event_id


def test_normalize_handles_missing_alert_block():
    payload = {
        "timestamp": "2026-04-27T19:14:32+0000",
        "event_type": "dns",
        "src_ip": "10.10.50.50",
        "dest_ip": "1.1.1.1",
    }
    e = normalize(payload)
    assert e.event_type == "dns"
    assert e.sid is None
    assert e.severity is None
    assert e.signature is None


def test_normalize_falls_back_to_now_for_invalid_timestamp():
    payload = {"event_type": "alert", "timestamp": "not-a-date"}
    e = normalize(payload)
    assert e.timestamp.tzinfo is not None
    assert (datetime.now(tz=timezone.utc) - e.timestamp).total_seconds() < 5


def test_to_loki_labels_bounded(basic_event):
    e = normalize(basic_event)
    labels = e.to_loki_labels(action="tag")
    assert set(labels.keys()) == {"job", "host", "sid", "severity", "action"}
    assert labels["sid"] == "2027865"
    assert labels["action"] == "tag"
    assert "dest_ip" not in labels  # cardinality guard
