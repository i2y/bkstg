"""User entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class UserProfile(BaseModel):
    """User profile information."""

    displayName: str | None = None
    email: str | None = None
    picture: str | None = None


class UserSpec(BaseModel):
    """Spec for User entity."""

    profile: UserProfile = Field(default_factory=UserProfile)
    memberOf: list[str] = Field(default_factory=list, title="Member Of")


class User(BaseEntity):
    """User entity."""

    kind: Literal[EntityKind.USER] = EntityKind.USER
    spec: UserSpec
