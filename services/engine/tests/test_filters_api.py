def _create(client, headers, **overrides) -> dict:
    payload = {
        "name": "Telegram bot from media-server",
        "description": "Outbound Telegram bot API; verified safe",
        "action": "tag",
        "source_host": "10.10.50.42",
        "sid": 2027865,
        "match_mode": "exact",
    }
    payload.update(overrides)
    r = client.post("/filters", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list(client, auth_headers):
    rule = _create(client, auth_headers)
    assert rule["id"] >= 1
    assert rule["enabled"] is True
    assert rule["action"] == "tag"
    listed = client.get("/filters", headers=auth_headers).json()
    assert any(r["id"] == rule["id"] for r in listed)


def test_get_404_for_unknown(client, auth_headers):
    r = client.get("/filters/9999", headers=auth_headers)
    assert r.status_code == 404


def test_update_changes_action(client, auth_headers):
    rule = _create(client, auth_headers)
    upd = {**rule, "action": "hide", "tags": None}
    upd.pop("id")
    upd.pop("created_at")
    upd.pop("updated_at")
    upd.pop("hit_count")
    r = client.put(f"/filters/{rule['id']}", json=upd, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["action"] == "hide"


def test_lifecycle_disable_retire_unretire(client, auth_headers):
    rule = _create(client, auth_headers)
    rid = rule["id"]

    r = client.post(f"/filters/{rid}/disable", headers=auth_headers).json()
    assert r["enabled"] is False

    r = client.post(f"/filters/{rid}/retire", headers=auth_headers).json()
    assert r["retired"] is True
    assert r["enabled"] is False

    listed = client.get("/filters", headers=auth_headers).json()
    assert all(item["id"] != rid for item in listed), "retired filter should be hidden by default"

    listed = client.get("/filters?include_retired=true", headers=auth_headers).json()
    assert any(item["id"] == rid for item in listed)

    r = client.post(f"/filters/{rid}/unretire", headers=auth_headers).json()
    assert r["retired"] is False
    assert r["enabled"] is False  # unretire returns to disabled


def test_duplicate_creates_disabled_copy(client, auth_headers):
    rule = _create(client, auth_headers)
    r = client.post(f"/filters/{rule['id']}/duplicate", headers=auth_headers).json()
    assert r["id"] != rule["id"]
    assert r["name"].endswith("(copy)")
    assert r["enabled"] is False


def test_create_validates_host_subnet_exclusivity(client, auth_headers):
    r = client.post(
        "/filters",
        headers=auth_headers,
        json={
            "name": "bad",
            "action": "tag",
            "source_host": "10.0.0.1",
            "source_subnet": "10.0.0.0/8",
            "sid": 1,
        },
    )
    assert r.status_code == 422


def test_classifier_runs_after_filter_create(client, auth_headers, basic_event):
    # Hide rule: matching event must be dropped from the Loki push.
    _create(client, auth_headers, action="hide")
    sent_before = len(client._sent_to_loki)  # type: ignore[attr-defined]

    r = client.post("/ingest/event", json=basic_event, headers=auth_headers)
    assert r.status_code == 200
    sent_after = len(client._sent_to_loki)  # type: ignore[attr-defined]
    # Hidden -> Loki push skipped.
    assert sent_after == sent_before


def test_classifier_tags_event_when_action_is_tag(client, auth_headers, basic_event):
    rule = _create(client, auth_headers, action="tag")
    sent_before = len(client._sent_to_loki)  # type: ignore[attr-defined]

    client.post("/ingest/event", json=basic_event, headers=auth_headers)
    sent = client._sent_to_loki  # type: ignore[attr-defined]
    assert len(sent) == sent_before + 1
    assert sent[-1][1] == "tag"

    matches = client.get(f"/filters/{rule['id']}/matches", headers=auth_headers).json()
    assert len(matches) == 1
    assert matches[0]["decision"] == "tag"


def test_preview_against_ring(client, auth_headers, basic_event, dns_event):
    # Seed the ring buffer first.
    client.post("/ingest/event", json=basic_event, headers=auth_headers)
    client.post("/ingest/event", json=dns_event, headers=auth_headers)

    # Draft preview: matches the basic event (Telegram SID).
    r = client.post(
        "/filters/preview",
        json={
            "name": "draft",
            "action": "tag",
            "source_host": "10.10.50.42",
            "sid": 2027865,
        },
        headers=auth_headers,
    )
    body = r.json()
    assert body["match_count"] == 1
    assert body["scanned"] >= 2
    assert len(body["samples"]) == 1


def test_from_event_prefills_draft(client, auth_headers, basic_event):
    r = client.post("/ingest/event", json=basic_event, headers=auth_headers)
    eid = r.json()["event_id"]

    draft = client.post(
        "/filters/from-event",
        json={"event_id": eid, "fields": ["source_host", "sid", "destination", "destination_port"]},
        headers=auth_headers,
    ).json()
    assert draft["source_host"] == "10.10.50.42"
    assert draft["sid"] == 2027865
    assert draft["destination"] == "149.154.167.41"
    assert draft["destination_port"] == 443
    assert draft["action"] == "tag"


def test_stats_endpoint(client, auth_headers):
    _create(client, auth_headers)
    r = client.get("/stats/filters", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_filters"] >= 1
    assert body["active_filters"] >= 1
