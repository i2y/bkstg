"""Group entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class GroupProfile(BaseModel):
    """Group profile information."""

    displayName: str | None = None
    email: str | None = None
    picture: str | None = None


class GroupSpec(BaseModel):
    """Spec for Group entity."""

    type: str = Field(
        ..., title="Type", description="Group type (team, business-unit, etc)"
    )
    profile: GroupProfile = Field(default_factory=GroupProfile)
    parent: str | None = Field(default=None, title="Parent")
    children: list[str] = Field(default_factory=list, title="Children")
    members: list[str] = Field(default_factory=list, title="Members")


class Group(BaseEntity):
    """Team/group entity."""

    kind: Literal[EntityKind.GROUP] = EntityKind.GROUP
    spec: GroupSpec
