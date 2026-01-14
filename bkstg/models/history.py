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


class RankImpactEntry(BaseModel):
    """Single entity's rank change due to definition change."""

    entity_id: str
    before_value: float | None = None
    before_label: str | None = None
    after_value: float | None = None
    after_label: str | None = None
    change_type: str  # "improved", "degraded", "unchanged", "new", "removed"


class DefinitionChangeSnapshot(BaseModel):
    """Snapshot of all entity rank changes due to a definition change.

    Links a definition change (in definition_history) to the impact on all entities.
    """

    definition_change_id: int  # Reference to definition_history.id
    definition_type: str  # "rank" (or "score" for future use)
    definition_id: str  # The rank/score definition ID
    timestamp: str  # ISO 8601 format
    total_entities_affected: int
    impacts: list[RankImpactEntry] = Field(default_factory=list)
    scorecard_id: str | None = None  # For multi-scorecard support


class EntityRankImpactHistory(BaseModel):
    """All rank impacts for a specific entity due to definition changes."""

    entity_id: str
    impacts: list[RankImpactEntry] = Field(default_factory=list)
