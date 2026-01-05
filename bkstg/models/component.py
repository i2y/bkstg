"""Component entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class ComponentSpec(BaseModel):
    """Spec for Component entity."""

    type: str = Field(
        ..., title="Type", description="Component type (service, website, library)"
    )
    lifecycle: str = Field(
        ...,
        title="Lifecycle",
        description="Lifecycle stage (production, experimental, deprecated)",
    )
    owner: str = Field(..., title="Owner", description="Owner group or user reference")
    system: str | None = Field(
        default=None, title="System", description="Parent system reference"
    )
    subcomponentOf: str | None = Field(default=None, title="Subcomponent Of")
    providesApis: list[str] = Field(default_factory=list, title="Provides APIs")
    consumesApis: list[str] = Field(default_factory=list, title="Consumes APIs")
    dependsOn: list[str] = Field(default_factory=list, title="Depends On")


class Component(BaseEntity):
    """Software component entity."""

    kind: Literal[EntityKind.COMPONENT] = EntityKind.COMPONENT
    spec: ComponentSpec
