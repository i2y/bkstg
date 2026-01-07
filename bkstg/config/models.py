"""Configuration models for bkstg."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LocalSource(BaseModel):
    """Local directory catalog source."""

    type: Literal["local"] = "local"
    path: str = Field(..., description="Local path to catalogs directory")
    name: str = Field(..., description="Display name for this source")
    enabled: bool = Field(default=True)


class GitHubSource(BaseModel):
    """GitHub repository catalog source."""

    type: Literal["github"] = "github"
    owner: str = Field(..., description="GitHub repository owner/organization")
    repo: str = Field(..., description="GitHub repository name")
    branch: str = Field(default="main", description="Branch name")
    path: str = Field(default="", description="Path within repo to catalogs directory")
    name: str = Field(..., description="Display name for this source")
    enabled: bool = Field(default=True)

    # Sync settings
    sync_enabled: bool = Field(default=False, description="Enable bidirectional sync")
    auto_commit: bool = Field(default=True, description="Auto-commit on entity save")


CatalogSource = LocalSource | GitHubSource


class BkstgSettings(BaseModel):
    """Global settings."""

    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    max_workers: int = Field(default=5, description="Max parallel fetch workers")
    locale: str = Field(default="auto", description="UI language (auto, en, ja)")
    github_org: str | None = Field(
        default=None, description="Default GitHub organization for user/group import"
    )


class BkstgConfig(BaseModel):
    """Root configuration model."""

    version: int = Field(default=1)
    sources: list[CatalogSource] = Field(default_factory=list)
    settings: BkstgSettings = Field(default_factory=BkstgSettings)
