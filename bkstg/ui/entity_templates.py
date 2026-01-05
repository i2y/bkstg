"""Entity templates and field configurations for all 7 entity kinds."""

from dataclasses import dataclass
from typing import Literal

from ..models.base import EntityKind


@dataclass
class FieldConfig:
    """Configuration for a form field."""

    name: str
    label: str
    field_type: Literal[
        "text", "textarea", "select", "reference", "multi_reference", "tags"
    ]
    required: bool = False
    options: list[str] | None = None  # For select fields
    target_kinds: list[EntityKind] | None = None  # For reference fields
    placeholder: str = ""


# Field configurations for each entity kind
ENTITY_FIELD_CONFIGS: dict[EntityKind, list[FieldConfig]] = {
    EntityKind.COMPONENT: [
        FieldConfig(
            "type",
            "Type",
            "select",
            True,
            ["service", "website", "library", "documentation", "tool"],
        ),
        FieldConfig(
            "lifecycle",
            "Lifecycle",
            "select",
            True,
            ["experimental", "production", "deprecated"],
        ),
        FieldConfig(
            "owner",
            "Owner",
            "reference",
            True,
            target_kinds=[EntityKind.USER, EntityKind.GROUP],
        ),
        FieldConfig(
            "system",
            "System",
            "reference",
            False,
            target_kinds=[EntityKind.SYSTEM],
        ),
        FieldConfig(
            "subcomponentOf",
            "Subcomponent Of",
            "reference",
            False,
            target_kinds=[EntityKind.COMPONENT],
        ),
        FieldConfig(
            "providesApis",
            "Provides APIs",
            "multi_reference",
            False,
            target_kinds=[EntityKind.API],
        ),
        FieldConfig(
            "consumesApis",
            "Consumes APIs",
            "multi_reference",
            False,
            target_kinds=[EntityKind.API],
        ),
        FieldConfig(
            "dependsOn",
            "Depends On",
            "multi_reference",
            False,
            target_kinds=[EntityKind.COMPONENT, EntityKind.RESOURCE],
        ),
    ],
    EntityKind.API: [
        FieldConfig(
            "type",
            "Type",
            "select",
            True,
            ["openapi", "asyncapi", "graphql", "grpc"],
        ),
        FieldConfig(
            "lifecycle",
            "Lifecycle",
            "select",
            True,
            ["experimental", "production", "deprecated"],
        ),
        FieldConfig(
            "owner",
            "Owner",
            "reference",
            True,
            target_kinds=[EntityKind.USER, EntityKind.GROUP],
        ),
        FieldConfig(
            "system",
            "System",
            "reference",
            False,
            target_kinds=[EntityKind.SYSTEM],
        ),
        FieldConfig(
            "definition",
            "Definition",
            "textarea",
            True,
            placeholder="OpenAPI/AsyncAPI definition or $text reference",
        ),
    ],
    EntityKind.RESOURCE: [
        FieldConfig(
            "type",
            "Type",
            "select",
            True,
            ["database", "s3-bucket", "queue", "cache", "storage"],
        ),
        FieldConfig(
            "owner",
            "Owner",
            "reference",
            True,
            target_kinds=[EntityKind.USER, EntityKind.GROUP],
        ),
        FieldConfig(
            "system",
            "System",
            "reference",
            False,
            target_kinds=[EntityKind.SYSTEM],
        ),
        FieldConfig(
            "dependsOn",
            "Depends On",
            "multi_reference",
            False,
            target_kinds=[EntityKind.RESOURCE],
        ),
        FieldConfig(
            "dependencyOf",
            "Dependency Of",
            "multi_reference",
            False,
            target_kinds=[EntityKind.COMPONENT, EntityKind.RESOURCE],
        ),
    ],
    EntityKind.SYSTEM: [
        FieldConfig(
            "owner",
            "Owner",
            "reference",
            True,
            target_kinds=[EntityKind.USER, EntityKind.GROUP],
        ),
        FieldConfig(
            "domain",
            "Domain",
            "reference",
            False,
            target_kinds=[EntityKind.DOMAIN],
        ),
    ],
    EntityKind.DOMAIN: [
        FieldConfig(
            "owner",
            "Owner",
            "reference",
            True,
            target_kinds=[EntityKind.USER, EntityKind.GROUP],
        ),
        FieldConfig(
            "subdomainOf",
            "Subdomain Of",
            "reference",
            False,
            target_kinds=[EntityKind.DOMAIN],
        ),
    ],
    EntityKind.USER: [
        FieldConfig(
            "displayName",
            "Display Name",
            "text",
            False,
            placeholder="Full name",
        ),
        FieldConfig(
            "email",
            "Email",
            "text",
            False,
            placeholder="user@example.com",
        ),
        FieldConfig(
            "memberOf",
            "Member Of",
            "multi_reference",
            False,
            target_kinds=[EntityKind.GROUP],
        ),
    ],
    EntityKind.GROUP: [
        FieldConfig(
            "type",
            "Type",
            "select",
            True,
            ["team", "business-unit", "department", "product-area"],
        ),
        FieldConfig(
            "displayName",
            "Display Name",
            "text",
            False,
            placeholder="Team name",
        ),
        FieldConfig(
            "email",
            "Email",
            "text",
            False,
            placeholder="team@example.com",
        ),
        FieldConfig(
            "parent",
            "Parent Group",
            "reference",
            False,
            target_kinds=[EntityKind.GROUP],
        ),
        FieldConfig(
            "members",
            "Members",
            "multi_reference",
            False,
            target_kinds=[EntityKind.USER],
        ),
    ],
}


def get_default_template(kind: EntityKind) -> dict:
    """Get default entity template for a kind.

    Returns a dict that can be used to create a new entity YAML.
    """
    templates = {
        EntityKind.COMPONENT: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": "my-component",
                "description": "A new component",
                "tags": [],
            },
            "spec": {
                "type": "service",
                "lifecycle": "experimental",
                "owner": "",
            },
        },
        EntityKind.API: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "API",
            "metadata": {
                "name": "my-api",
                "description": "A new API",
                "tags": [],
            },
            "spec": {
                "type": "openapi",
                "lifecycle": "experimental",
                "owner": "",
                "definition": "openapi: 3.0.0\ninfo:\n  title: My API\n  version: 1.0.0",
            },
        },
        EntityKind.RESOURCE: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Resource",
            "metadata": {
                "name": "my-resource",
                "description": "A new resource",
                "tags": [],
            },
            "spec": {
                "type": "database",
                "owner": "",
            },
        },
        EntityKind.SYSTEM: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "System",
            "metadata": {
                "name": "my-system",
                "description": "A new system",
                "tags": [],
            },
            "spec": {
                "owner": "",
            },
        },
        EntityKind.DOMAIN: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Domain",
            "metadata": {
                "name": "my-domain",
                "description": "A new domain",
                "tags": [],
            },
            "spec": {
                "owner": "",
            },
        },
        EntityKind.USER: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "User",
            "metadata": {
                "name": "username",
                "description": "",
                "tags": [],
            },
            "spec": {
                "profile": {
                    "displayName": "",
                    "email": "",
                },
                "memberOf": [],
            },
        },
        EntityKind.GROUP: {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "metadata": {
                "name": "my-team",
                "description": "A new team",
                "tags": [],
            },
            "spec": {
                "type": "team",
                "profile": {
                    "displayName": "",
                    "email": "",
                },
                "members": [],
            },
        },
    }
    return templates.get(kind, templates[EntityKind.COMPONENT])
