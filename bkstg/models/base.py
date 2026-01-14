"""Base models for Backstage entities."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EntityKind(str, Enum):
    """Supported entity kinds."""

    COMPONENT = "Component"
    API = "API"
    RESOURCE = "Resource"
    SYSTEM = "System"
    DOMAIN = "Domain"
    USER = "User"
    GROUP = "Group"
    LOCATION = "Location"

    @classmethod
    def from_str(cls, value: str) -> "EntityKind":
        """Parse entity kind from string, handling case insensitivity."""
        normalized = value.lower()
        if normalized == "component":
            return cls.COMPONENT
        elif normalized == "api":
            return cls.API
        elif normalized == "resource":
            return cls.RESOURCE
        elif normalized == "system":
            return cls.SYSTEM
        elif normalized == "domain":
            return cls.DOMAIN
        elif normalized == "user":
            return cls.USER
        elif normalized == "group":
            return cls.GROUP
        elif normalized == "location":
            return cls.LOCATION
        else:
            return cls(value)


class EntityRef(BaseModel):
    """Reference to another entity (kind:namespace/name format)."""

    kind: EntityKind
    namespace: str = "default"
    name: str

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.namespace}/{self.name}"

    @classmethod
    def parse(cls, ref_str: str) -> "EntityRef":
        """Parse entity reference string.

        Formats:
        - kind:namespace/name
        - kind:name (uses default namespace)
        - name (assumes Component kind and default namespace)
        """
        if ":" in ref_str:
            kind_part, rest = ref_str.split(":", 1)
            kind = EntityKind.from_str(kind_part)
            if "/" in rest:
                namespace, name = rest.split("/", 1)
            else:
                namespace = "default"
                name = rest
        else:
            kind = EntityKind.COMPONENT
            namespace = "default"
            name = ref_str

        return cls(kind=kind, namespace=namespace, name=name)

    def to_id(self) -> str:
        """Convert to unique ID string."""
        return f"{self.kind.value}:{self.namespace}/{self.name}"


class EntityLink(BaseModel):
    """External link for an entity."""

    url: str
    title: str | None = None
    icon: str | None = None
    type: str | None = None


class ScoreValue(BaseModel):
    """Individual score entry for an entity (bkstg extension).

    For multi-scorecard support, scorecard_id specifies which scorecard this score
    belongs to. If None, it belongs to the default scorecard.
    """

    score_id: str
    value: float
    reason: str | None = None
    updated_at: str | None = None
    scorecard_id: str | None = None  # For multi-scorecard support

    def is_na(self) -> bool:
        """Check if this score is N/A (value == -1)."""
        return self.value == -1.0


class EntityMetadata(BaseModel):
    """Common metadata for all entities."""

    name: str = Field(..., title="Name", description="Unique entity name")
    namespace: str = Field(default="default", title="Namespace")
    title: str | None = Field(
        default=None, title="Title", description="Human-readable title"
    )
    description: str | None = Field(default=None, title="Description")
    labels: dict[str, str] = Field(default_factory=dict, title="Labels")
    annotations: dict[str, str] = Field(default_factory=dict, title="Annotations")
    tags: list[str] = Field(default_factory=list, title="Tags")
    links: list[EntityLink] = Field(default_factory=list, title="Links")
    # bkstg extension: scores (not part of Backstage standard schema)
    scores: list["ScoreValue"] = Field(default_factory=list, title="Scores")


class BaseEntity(BaseModel):
    """Base class for all Backstage entities."""

    apiVersion: str = "backstage.io/v1alpha1"
    kind: EntityKind
    metadata: EntityMetadata

    @property
    def ref(self) -> EntityRef:
        """Get entity reference."""
        return EntityRef(
            kind=self.kind,
            namespace=self.metadata.namespace,
            name=self.metadata.name,
        )

    @property
    def entity_id(self) -> str:
        """Get unique entity ID."""
        return self.ref.to_id()

    def model_post_init(self, __context: Any) -> None:
        """Validate kind matches the entity type."""
        pass
