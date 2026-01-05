"""Catalog container for all entities."""

from typing import Union

from pydantic import BaseModel, Field

from .api import API
from .base import EntityKind, EntityRef
from .component import Component
from .domain import Domain
from .group import Group
from .location import Location
from .resource import Resource
from .system import System
from .user import User

Entity = Union[Component, API, Resource, System, Domain, User, Group, Location]


class Catalog(BaseModel):
    """Container for all catalog entities."""

    components: dict[str, Component] = Field(default_factory=dict)
    apis: dict[str, API] = Field(default_factory=dict)
    resources: dict[str, Resource] = Field(default_factory=dict)
    systems: dict[str, System] = Field(default_factory=dict)
    domains: dict[str, Domain] = Field(default_factory=dict)
    users: dict[str, User] = Field(default_factory=dict)
    groups: dict[str, Group] = Field(default_factory=dict)
    locations: dict[str, Location] = Field(default_factory=dict)

    def add_entity(self, entity: Entity) -> None:
        """Add an entity to the catalog."""
        key = entity.entity_id
        match entity.kind:
            case EntityKind.COMPONENT:
                self.components[key] = entity
            case EntityKind.API:
                self.apis[key] = entity
            case EntityKind.RESOURCE:
                self.resources[key] = entity
            case EntityKind.SYSTEM:
                self.systems[key] = entity
            case EntityKind.DOMAIN:
                self.domains[key] = entity
            case EntityKind.USER:
                self.users[key] = entity
            case EntityKind.GROUP:
                self.groups[key] = entity
            case EntityKind.LOCATION:
                self.locations[key] = entity

    def get_entity(self, ref: EntityRef) -> Entity | None:
        """Get entity by reference."""
        key = ref.to_id()
        match ref.kind:
            case EntityKind.COMPONENT:
                return self.components.get(key)
            case EntityKind.API:
                return self.apis.get(key)
            case EntityKind.RESOURCE:
                return self.resources.get(key)
            case EntityKind.SYSTEM:
                return self.systems.get(key)
            case EntityKind.DOMAIN:
                return self.domains.get(key)
            case EntityKind.USER:
                return self.users.get(key)
            case EntityKind.GROUP:
                return self.groups.get(key)
            case EntityKind.LOCATION:
                return self.locations.get(key)
        return None

    def get_entity_by_id(self, entity_id: str) -> Entity | None:
        """Get entity by ID string."""
        ref = EntityRef.parse(entity_id)
        return self.get_entity(ref)

    def all_entities(self) -> list[Entity]:
        """Return all entities as a flat list."""
        return [
            *self.components.values(),
            *self.apis.values(),
            *self.resources.values(),
            *self.systems.values(),
            *self.domains.values(),
            *self.users.values(),
            *self.groups.values(),
            *self.locations.values(),
        ]

    def entities_by_kind(self, kind: EntityKind) -> list[Entity]:
        """Get all entities of a specific kind."""
        match kind:
            case EntityKind.COMPONENT:
                return list(self.components.values())
            case EntityKind.API:
                return list(self.apis.values())
            case EntityKind.RESOURCE:
                return list(self.resources.values())
            case EntityKind.SYSTEM:
                return list(self.systems.values())
            case EntityKind.DOMAIN:
                return list(self.domains.values())
            case EntityKind.USER:
                return list(self.users.values())
            case EntityKind.GROUP:
                return list(self.groups.values())
            case EntityKind.LOCATION:
                return list(self.locations.values())
        return []

    def count(self) -> dict[str, int]:
        """Get entity count by kind."""
        return {
            "Component": len(self.components),
            "API": len(self.apis),
            "Resource": len(self.resources),
            "System": len(self.systems),
            "Domain": len(self.domains),
            "User": len(self.users),
            "Group": len(self.groups),
            "Location": len(self.locations),
            "Total": len(self.all_entities()),
        }
