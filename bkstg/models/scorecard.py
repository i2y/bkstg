"""Scorecard models for bkstg (bkstg extension, not Backstage standard)."""

from pydantic import BaseModel, Field

# ScoreValue is defined in base.py to avoid circular imports
from .base import ScoreValue  # noqa: F401 - re-export


class ScoreDefinition(BaseModel):
    """Definition of a score type."""

    id: str = Field(..., description="Unique score ID")
    name: str = Field(..., description="Human-readable name")
    description: str | None = Field(default=None)
    target_kinds: list[str] = Field(
        default_factory=list,
        description="Entity kinds this score applies to (empty = all)",
    )
    min_value: float = Field(default=0.0)
    max_value: float = Field(default=100.0)


class RankThreshold(BaseModel):
    """Threshold for rank label assignment."""

    min: float = Field(..., description="Minimum value for this label (inclusive)")
    label: str = Field(..., description="Rank label (e.g., S, A, B, C, D)")


class RankDefinition(BaseModel):
    """Definition of a rank calculation."""

    id: str = Field(..., description="Unique rank ID")
    name: str = Field(..., description="Human-readable name")
    description: str | None = Field(default=None)
    target_kinds: list[str] = Field(
        default_factory=list,
        description="Entity kinds this rank applies to",
    )
    score_refs: list[str] = Field(
        default_factory=list,
        description="Score IDs referenced in the formula",
    )
    formula: str = Field(..., description="Python expression for calculation")
    thresholds: list[RankThreshold] = Field(
        default_factory=list,
        description="Thresholds for rank labels (sorted by min descending)",
    )

    def get_label(self, value: float) -> str:
        """Get rank label for a given value."""
        # Sort thresholds by min descending
        sorted_thresholds = sorted(self.thresholds, key=lambda t: t.min, reverse=True)
        for threshold in sorted_thresholds:
            if value >= threshold.min:
                return threshold.label
        return sorted_thresholds[-1].label if sorted_thresholds else ""


class ScorecardDefinitionSpec(BaseModel):
    """Spec for ScorecardDefinition entity."""

    scores: list[ScoreDefinition] = Field(default_factory=list)
    ranks: list[RankDefinition] = Field(default_factory=list)


class ScorecardDefinitionMetadata(BaseModel):
    """Metadata for ScorecardDefinition."""

    name: str
    title: str | None = None
    description: str | None = None


class ScorecardDefinition(BaseModel):
    """Scorecard definition entity (kind: ScorecardDefinition)."""

    apiVersion: str = "bkstg.io/v1alpha1"
    kind: str = "ScorecardDefinition"
    metadata: ScorecardDefinitionMetadata
    spec: ScorecardDefinitionSpec
