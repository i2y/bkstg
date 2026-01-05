"""API entity model."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind


class APISpec(BaseModel):
    """Spec for API entity."""

    type: str = Field(
        ..., title="Type", description="API type (openapi, asyncapi, graphql, grpc)"
    )
    lifecycle: str = Field(..., title="Lifecycle")
    owner: str = Field(..., title="Owner")
    system: str | None = Field(default=None, title="System")
    definition: str = Field(
        ..., title="Definition", description="API specification (inline or URL)"
    )


class API(BaseEntity):
    """API interface entity."""

    kind: Literal[EntityKind.API] = EntityKind.API
    spec: APISpec
