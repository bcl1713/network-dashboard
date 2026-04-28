from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Action = Literal["tag", "hide", "allow"]
MatchMode = Literal["exact", "contains", "regex"]
Decision_t = Literal["tag", "hide", "allow", "passthrough"]


class FilterBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    enabled: bool = True
    action: Action = "tag"

    source_host: str | None = None
    source_subnet: str | None = None
    sid: int | None = None
    generator_id: int | None = None
    destination: str | None = None
    destination_subnet: str | None = None
    destination_port: int | None = Field(default=None, ge=0, le=65535)
    protocol: str | None = None
    message_match: str | None = None
    match_mode: MatchMode = "exact"

    tags: list[str] | None = None
    expires_at: datetime | None = None
    notes: str | None = None
    created_by: str | None = None

    @field_validator("expires_at", mode="before")
    @classmethod
    def _coerce_expires_at(cls, v: Any) -> Any:
        if isinstance(v, str) and (v == "" or v == "None"):
            return None
        return v

    @model_validator(mode="after")
    def _exclusive_host_subnet(self):
        if self.source_host and self.source_subnet:
            raise ValueError("source_host and source_subnet are mutually exclusive")
        if self.destination and self.destination_subnet:
            raise ValueError("destination and destination_subnet are mutually exclusive")
        return self


class FilterCreate(FilterBase):
    pass


class FilterUpdate(FilterBase):
    pass


class FilterOut(FilterBase):
    id: int
    retired: bool = False
    enabled: bool
    created_at: datetime
    updated_at: datetime
    hit_count: int
    last_seen_at: datetime | None = None
    last_matched_event_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_tags(cls, data: Any) -> Any:
        # ORM returns tags as a JSON-encoded text column.
        if hasattr(data, "tags"):
            obj = {c: getattr(data, c) for c in data.__table__.columns.keys()}
            obj["enabled"] = bool(obj.get("enabled"))
            obj["retired"] = bool(obj.get("retired"))
            tags = obj.get("tags")
            if isinstance(tags, str) and tags:
                try:
                    obj["tags"] = json.loads(tags)
                except json.JSONDecodeError:
                    obj["tags"] = [tags]
            elif tags is None:
                obj["tags"] = None
            return obj
        if isinstance(data, dict) and isinstance(data.get("tags"), str) and data["tags"]:
            try:
                data["tags"] = json.loads(data["tags"])
            except json.JSONDecodeError:
                pass
        return data


class FilterListItem(FilterOut):
    pass


class FilterPreviewRequest(BaseModel):
    """Either supply an event_id (preview against that event) or rely on the
    full ring-buffer scan."""
    event_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)


class FilterPreviewSample(BaseModel):
    event_id: str
    timestamp: datetime
    src_ip: str | None
    dest_ip: str | None
    sid: int | None
    signature: str | None


class FilterPreviewResponse(BaseModel):
    match_count: int
    scanned: int
    samples: list[FilterPreviewSample]


class FromEventRequest(BaseModel):
    event_id: str
    fields: list[Literal["source_host", "sid", "destination", "destination_port", "protocol"]] = Field(
        default_factory=lambda: ["source_host", "sid"]
    )
    action: Action = "tag"
    name: str | None = None


class DecisionOut(BaseModel):
    action: Decision_t
    filter_id: int | None
    matched_fields: dict[str, Any]


class WhyHiddenStep(BaseModel):
    filter_id: int
    name: str
    action: Action
    matched: bool
    matched_fields: dict[str, Any]


class WhyHiddenResponse(BaseModel):
    event_id: str
    decision: DecisionOut
    chain: list[WhyHiddenStep]


class StatsRow(BaseModel):
    sid: int | None
    hits_24h: int
    last_seen_at: datetime | None


class StatsResponse(BaseModel):
    total_filters: int
    active_filters: int
    retired_filters: int
    total_hits_24h: int
    top_sids: list[StatsRow]
