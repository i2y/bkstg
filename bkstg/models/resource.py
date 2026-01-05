"""Resource entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class ResourceSpec(BaseModel):
    """Spec for Resource entity."""

    type: str = Field(
        ..., title="Type", description="Resource type (database, s3-bucket, etc)"
    )
    owner: str = Field(..., title="Owner")
    system: str | None = Field(default=None, title="System")
    dependsOn: list[str] = Field(default_factory=list, title="Depends On")
    dependencyOf: list[str] = Field(default_factory=list, title="Dependency Of")


class Resource(BaseEntity):
    """Infrastructure resource entity."""

    kind: Literal[EntityKind.RESOURCE] = EntityKind.RESOURCE
    spec: ResourceSpec
