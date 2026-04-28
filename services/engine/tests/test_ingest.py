def test_ingest_event_requires_token(client, basic_event):
    r = client.post("/ingest/event", json=basic_event)
    assert r.status_code == 401


def test_ingest_event_accepts_basic_event(client, auth_headers, basic_event):
    r = client.post("/ingest/event", json=basic_event, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["event_id"]

    sent = client._sent_to_loki  # type: ignore[attr-defined]
    assert len(sent) == 1
    assert sent[0][1] == "passthrough"  # Phase 1: classifier unset


def test_ingest_event_lookup_via_events_endpoint(client, auth_headers, basic_event):
    r = client.post("/ingest/event", json=basic_event, headers=auth_headers)
    event_id = r.json()["event_id"]
    g = client.get(f"/events/{event_id}", headers=auth_headers)
    assert g.status_code == 200
    body = g.json()
    assert body["sid"] == 2027865
    assert body["src_ip"] == "10.10.50.42"


def test_ingest_event_rejects_non_object(client, auth_headers):
    r = client.post("/ingest/event", json=["not", "an", "object"], headers=auth_headers)
    assert r.status_code == 400


def test_ingest_event_rejects_invalid_json(client, auth_headers):
    r = client.post(
        "/ingest/event",
        content="not json",
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_ingest_bulk_ndjson(client, auth_headers, basic_event, dns_event):
    import json

    body = "\n".join(json.dumps(e) for e in (basic_event, dns_event))
    r = client.post(
        "/ingest/bulk",
        content=body,
        headers={**auth_headers, "Content-Type": "application/x-ndjson"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["accepted"] == 2
    assert len(out["event_ids"]) == 2
    sent = client._sent_to_loki  # type: ignore[attr-defined]
    assert len(sent) == 2


def test_ingest_bulk_json_array(client, auth_headers, basic_event, dns_event):
    r = client.post("/ingest/bulk", json=[basic_event, dns_event], headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["accepted"] == 2


def test_event_lookup_404_for_unknown(client, auth_headers):
    r = client.get("/events/does-not-exist", headers=auth_headers)
    assert r.status_code == 404


def test_why_hidden_returns_chain(client, auth_headers, basic_event):
    r = client.post("/ingest/event", json=basic_event, headers=auth_headers)
    eid = r.json()["event_id"]
    r2 = client.get(f"/events/{eid}/why-hidden", headers=auth_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["event_id"] == eid
    # No rules seeded -> passthrough decision and empty consideration chain.
    assert body["decision"]["action"] == "passthrough"
    assert body["chain"] == []


def test_healthz_no_token_required(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
