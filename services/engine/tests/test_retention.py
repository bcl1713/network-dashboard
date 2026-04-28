from datetime import datetime, timedelta, timezone


def test_prune_only_removes_old_audit_rows(client, auth_headers, basic_event):
    # Create a hide rule and ingest a matching event so an audit row exists.
    create = client.post(
        "/filters",
        json={
            "name": "telegram",
            "action": "tag",
            "source_host": "10.10.50.42",
            "sid": 2027865,
            "match_mode": "exact",
        },
        headers=auth_headers,
    )
    assert create.status_code == 201
    fid = create.json()["id"]

    client.post("/ingest/event", json=basic_event, headers=auth_headers)

    # Sanity: one matching audit row.
    matches = client.get(f"/filters/{fid}/matches", headers=auth_headers).json()
    assert len(matches) == 1

    # Backdate the row so prune_once removes it.
    from app.db import session_scope
    from app.models import FilterAudit

    old = datetime.now(tz=timezone.utc) - timedelta(days=60)
    with session_scope() as session:
        row = session.query(FilterAudit).first()
        row.matched_at = old.replace(tzinfo=None)
        session.commit()

    from app.retention import prune_once

    deleted = prune_once(ttl_days=30)
    assert deleted == 1

    matches_after = client.get(f"/filters/{fid}/matches", headers=auth_headers).json()
    assert matches_after == []


def test_prune_keeps_recent_rows(client, auth_headers, basic_event):
    create = client.post(
        "/filters",
        json={
            "name": "telegram",
            "action": "tag",
            "source_host": "10.10.50.42",
            "sid": 2027865,
            "match_mode": "exact",
        },
        headers=auth_headers,
    )
    fid = create.json()["id"]
    client.post("/ingest/event", json=basic_event, headers=auth_headers)

    from app.retention import prune_once

    deleted = prune_once(ttl_days=30)
    assert deleted == 0
    assert len(client.get(f"/filters/{fid}/matches", headers=auth_headers).json()) == 1
