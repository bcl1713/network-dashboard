def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Overview" in r.text
    assert "Active filters" in r.text


def test_filters_list_empty(client):
    r = client.get("/filters")
    assert r.status_code == 200
    assert "No filters yet" in r.text


def test_filters_new_form(client):
    r = client.get("/filters/new")
    assert r.status_code == 200
    assert "New filter" in r.text
    assert 'name="name"' in r.text


def test_filters_create_redirects(client, fake_engine):
    r = client.post(
        "/filters/new",
        data={
            "name": "Telegram noise",
            "action": "tag",
            "match_mode": "exact",
            "source_host": "10.10.50.42",
            "sid": "2027865",
            "enabled": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/filters/")
    assert len(fake_engine.filters) == 1


def test_filters_list_shows_created(client, fake_engine):
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        fake_engine.create_filter({"name": "x", "action": "tag", "sid": 1})
    )
    r = client.get("/filters")
    assert r.status_code == 200
    assert "x" in r.text
    assert "SID 1" in r.text


def test_filters_detail_404(client):
    r = client.get("/filters/9999")
    assert r.status_code == 404


def test_event_detail_renders_create_link(client, fake_engine):
    fake_engine.events["abc"] = {
        "event_id": "abc",
        "timestamp": "2026-04-27T00:00:00",
        "event_type": "alert",
        "src_ip": "10.10.50.42",
        "src_port": 1234,
        "dest_ip": "1.2.3.4",
        "dest_port": 443,
        "proto": "TCP",
        "sid": 1,
        "generator_id": 1,
        "signature": "sig",
        "severity": 2,
        "host": "h",
        "geoip_country": None,
        "geoip_city": None,
        "raw": {"a": 1},
    }
    r = client.get("/events/abc")
    assert r.status_code == 200
    assert "Create safe filter from this event" in r.text
    assert "/filters/new?from_event=abc" in r.text


def test_htmx_lifecycle_returns_row_fragment(client, fake_engine):
    import asyncio

    rule = asyncio.get_event_loop().run_until_complete(
        fake_engine.create_filter({"name": "x", "action": "tag", "sid": 1})
    )
    r = client.post(
        f"/htmx/filters/{rule['id']}/lifecycle",
        data={"action": "disable"},
    )
    assert r.status_code == 200
    assert f'id="filter-row-{rule["id"]}"' in r.text
    assert "disabled" in r.text.lower()
