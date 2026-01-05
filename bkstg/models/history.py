"""History models for score and rank tracking."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreHistoryEntry(BaseModel):
    """Single score history entry."""

    timestamp: str  # ISO 8601 format
    value: float
    reason: str | None = None
    source: str | None = None  # "manual", "automated", "imported"


class ScoreHistory(BaseModel):
    """History of a specific score for an entity."""

    score_id: str
    entries: list[ScoreHistoryEntry] = Field(default_factory=list)


class EntityScoreHistory(BaseModel):
    """All score histories for an entity."""

    entity_id: str
    scores: dict[str, ScoreHistory] = Field(default_factory=dict)


class RankHistoryEntry(BaseModel):
    """Single rank history entry."""

    timestamp: str  # ISO 8601 format
    value: float
    label: str | None = None
    score_snapshot: dict[str, float] = Field(default_factory=dict)


class RankHistory(BaseModel):
    """History of a specific rank for an entity."""

    rank_id: str
    entries: list[RankHistoryEntry] = Field(default_factory=list)


class EntityRankHistory(BaseModel):
    """All rank histories for an entity."""

    entity_id: str
    ranks: dict[str, RankHistory] = Field(default_factory=dict)


class DefinitionChangeEntry(BaseModel):
    """Single definition change entry."""

    timestamp: str  # ISO 8601 format
    change_type: str  # "created", "updated", "deleted"
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    changed_fields: list[str] = Field(default_factory=list)


class ScoreDefinitionHistory(BaseModel):
    """History of changes to a score definition."""

    score_id: str
    entries: list[DefinitionChangeEntry] = Field(default_factory=list)


class RankDefinitionHistory(BaseModel):
    """History of changes to a rank definition."""

    rank_id: str
    entries: list[DefinitionChangeEntry] = Field(default_factory=list)


class AllScoreDefinitionHistories(BaseModel):
    """All score definition change histories."""

    scores: dict[str, ScoreDefinitionHistory] = Field(default_factory=dict)


class AllRankDefinitionHistories(BaseModel):
    """All rank definition change histories."""

    ranks: dict[str, RankDefinitionHistory] = Field(default_factory=dict)
