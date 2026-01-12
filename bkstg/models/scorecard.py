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


class RankRule(BaseModel):
    """A conditional rule for rank calculation.

    Rules are evaluated in order; the first matching rule's formula is used.
    A rule without a condition (or condition="True") is a default rule.
    """

    condition: str | None = Field(
        default=None,
        description="Python expression for condition (uses entity.* for attributes)",
    )
    formula: str = Field(..., description="Python expression for rank calculation")
    description: str | None = Field(default=None)


class RankDefinition(BaseModel):
    """Definition of a rank calculation.

    Supports three modes:
    1. Simple mode: Use 'formula' field directly (backwards compatible)
       - Formula returns numeric value, mapped to label via thresholds
    2. Conditional mode: Use 'rules' field with ordered conditional rules
       - Each rule has optional condition + formula
       - First matching rule's formula is used, mapped via thresholds
    3. Label function mode: Use 'label_function' field
       - Python code with if/elif/else that directly returns label strings
       - Bypasses thresholds entirely

    When using conditional or label function modes, 'entity_refs' lists which
    entity attributes are referenced (for validation and optimization).
    """

    id: str = Field(..., description="Unique rank ID")
    name: str = Field(..., description="Human-readable name")
    description: str | None = Field(default=None)
    target_kinds: list[str] = Field(
        default_factory=list,
        description="Entity kinds this rank applies to",
    )
    score_refs: list[str] = Field(
        default_factory=list,
        description="Score IDs referenced in the formula(s)",
    )

    # Mode 1: Simple formula (backwards compatible)
    formula: str | None = Field(
        default=None,
        description="Python expression for calculation (simple mode)",
    )

    # Mode 2: Conditional rules
    rules: list[RankRule] | None = Field(
        default=None,
        description="Ordered list of conditional rules (conditional mode)",
    )

    # Mode 3: Label function (direct label return)
    label_function: str | None = Field(
        default=None,
        description="Python code with if/elif/else that directly returns label strings",
    )

    # Entity attributes referenced in conditions/label_function
    entity_refs: list[str] = Field(
        default_factory=list,
        description="Entity attributes referenced (kind, type, lifecycle, tags, etc.)",
    )

    thresholds: list[RankThreshold] = Field(
        default_factory=list,
        description="Thresholds for rank labels (only for simple/conditional modes)",
    )

    def get_label(self, value: float) -> str:
        """Get rank label for a given value."""
        # Sort thresholds by min descending
        sorted_thresholds = sorted(self.thresholds, key=lambda t: t.min, reverse=True)
        for threshold in sorted_thresholds:
            if value >= threshold.min:
                return threshold.label
        return sorted_thresholds[-1].label if sorted_thresholds else ""

    def has_conditional_rules(self) -> bool:
        """Check if this definition uses conditional rules (mode 2)."""
        return bool(self.rules)

    def has_label_function(self) -> bool:
        """Check if this definition uses label function (mode 3)."""
        return bool(self.label_function)

    def get_mode(self) -> str:
        """Get the calculation mode.

        Returns:
            'label_function' for mode 3, 'conditional' for mode 2, 'simple' for mode 1
        """
        if self.label_function:
            return "label_function"
        elif self.rules:
            return "conditional"
        else:
            return "simple"


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
