"""Pydantic models for Backstage entities."""

from .base import EntityKind, EntityRef, EntityMetadata, EntityLink, BaseEntity, ScoreValue
from .component import Component, ComponentSpec
from .api import API, APISpec
from .resource import Resource, ResourceSpec
from .system import System, SystemSpec
from .domain import Domain, DomainSpec
from .user import User, UserSpec, UserProfile
from .group import Group, GroupSpec
from .catalog import Catalog, Entity
from .scorecard import (
    ScoreDefinition,
    RankDefinition,
    RankThreshold,
    ScorecardDefinition,
    ScorecardDefinitionSpec,
    ScorecardDefinitionMetadata,
)

__all__ = [
    "EntityKind",
    "EntityRef",
    "EntityMetadata",
    "EntityLink",
    "BaseEntity",
    "ScoreValue",
    "Component",
    "ComponentSpec",
    "API",
    "APISpec",
    "Resource",
    "ResourceSpec",
    "System",
    "SystemSpec",
    "Domain",
    "DomainSpec",
    "User",
    "UserSpec",
    "UserProfile",
    "Group",
    "GroupSpec",
    "Catalog",
    "Entity",
    "ScoreDefinition",
    "RankDefinition",
    "RankThreshold",
    "ScorecardDefinition",
    "ScorecardDefinitionSpec",
    "ScorecardDefinitionMetadata",
]
