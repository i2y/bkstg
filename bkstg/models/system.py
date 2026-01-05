"""System entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class SystemSpec(BaseModel):
    """Spec for System entity."""

    owner: str = Field(..., title="Owner")
    domain: str | None = Field(default=None, title="Domain")


class System(BaseEntity):
    """System grouping entity."""

    kind: Literal[EntityKind.SYSTEM] = EntityKind.SYSTEM
    spec: SystemSpec
