from datetime import datetime, timezone

from app.eve import NormalizedEvent
from app.ring_buffer import RingBuffer


def _ev(eid: str) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=eid,
        timestamp=datetime.now(tz=timezone.utc),
        event_type="alert",
        src_ip="10.0.0.1",
        src_port=1,
        dest_ip="10.0.0.2",
        dest_port=80,
        proto="TCP",
        sid=1,
        generator_id=1,
        signature="x",
        severity=1,
        host="h",
        geoip_country=None,
        geoip_city=None,
        raw={},
    )


def test_append_and_get():
    rb = RingBuffer(maxlen=3)
    rb.append(_ev("a"))
    rb.append(_ev("b"))
    assert rb.get("a").event_id == "a"
    assert rb.get("missing") is None
    assert len(rb) == 2


def test_eviction_drops_oldest_from_index():
    rb = RingBuffer(maxlen=2)
    rb.append(_ev("a"))
    rb.append(_ev("b"))
    rb.append(_ev("c"))
    assert rb.get("a") is None
    assert rb.get("b") is not None
    assert rb.get("c") is not None
    assert len(rb) == 2


def test_snapshot_returns_copy():
    rb = RingBuffer(maxlen=10)
    rb.append(_ev("a"))
    snap = rb.snapshot()
    rb.append(_ev("b"))
    assert len(snap) == 1
