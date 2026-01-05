"""Domain entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class DomainSpec(BaseModel):
    """Spec for Domain entity."""

    owner: str = Field(..., title="Owner")
    subdomainOf: str | None = Field(default=None, title="Subdomain Of")


class Domain(BaseEntity):
    """Bounded context domain entity."""

    kind: Literal[EntityKind.DOMAIN] = EntityKind.DOMAIN
    spec: DomainSpec
