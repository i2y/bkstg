"""Location entity model for referencing external catalog sources."""

from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseEntity, EntityKind, EntityMetadata


class LocationSpec(BaseModel):
    """Specification for a Location entity."""

    type: str | None = Field(
        default=None,
        title="Type",
        description="Location type (url or file). Inherits from parent if not specified.",
    )
    target: str | None = Field(
        default=None,
        title="Target",
        description="Single target URL or file path.",
    )
    targets: list[str] = Field(
        default_factory=list,
        title="Targets",
        description="Multiple target URLs or file paths.",
    )
    presence: Literal["required", "optional"] = Field(
        default="required",
        title="Presence",
        description="Whether the target must exist (required) or is optional.",
    )


class Location(BaseEntity):
    """Location entity for referencing external catalog sources.

    Location entities point to other YAML files that contain catalog entities.
    They support both local file references and remote GitHub URLs.

    Example:
        apiVersion: backstage.io/v1alpha1
        kind: Location
        metadata:
          name: external-catalog
        spec:
          type: url
          target: https://github.com/org/repo/blob/main/catalog-info.yaml
    """

    kind: Literal[EntityKind.LOCATION] = EntityKind.LOCATION
    spec: LocationSpec

    def get_all_targets(self) -> list[str]:
        """Get all targets (combining target and targets)."""
        result = []
        if self.spec.target:
            result.append(self.spec.target)
        result.extend(self.spec.targets)
        return result
