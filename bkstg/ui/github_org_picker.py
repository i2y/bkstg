"""GitHub Organization entity picker component."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

from castella import (
    Button,
    Column,
    Component,
    DataTable,
    DataTableState,
    Input,
    InputState,
    Row,
    Spacer,
    State,
    Text,
)
from castella.theme import ThemeManager

from ..git.github_org_api import GitHubMember, GitHubOrgAPI, GitHubTeam
from ..i18n import t
from ..models.base import EntityKind

if TYPE_CHECKING:
    pass


class GitHubMemberRow(BaseModel):
    """Row model for GitHub member table."""

    login: str = Field(title="Login")
    name: str = Field(title="Name")


class GitHubTeamRow(BaseModel):
    """Row model for GitHub team table."""

    slug: str = Field(title="Slug")
    name: str = Field(title="Name")
    description: str = Field(title="Description")


class GitHubOrgPicker(Component):
    """Picker for GitHub organization members and teams."""

    def __init__(
        self,
        org: str,
        target_kinds: list[EntityKind],
        on_select: Callable[[dict], None],
        on_close: Callable[[], None],
    ):
        super().__init__()
        self._org = org
        self._target_kinds = target_kinds
        self._on_select = on_select
        self._on_close = on_close

        self._api = GitHubOrgAPI(org)
        self._search_state = InputState("")
        self._search_state.attach(self)

        self._loading = State(True)
        self._loading.attach(self)
        self._error = State("")
        self._error.attach(self)

        self._members: list[GitHubMember] = []
        self._teams: list[GitHubTeam] = []

        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        self._data_loaded = False

    def _do_load_data(self):
        """Load members/teams from GitHub (called from view on first render)."""
        # Check auth
        if not self._api.check_auth_status():
            self._error.set(t("github.auth_required"))
            self._loading.set(False)
            return

        # Check org access
        if not self._api.check_org_access():
            self._error.set(t("github.org_access_denied", org=self._org))
            self._loading.set(False)
            return

        # Load based on target kinds
        if EntityKind.USER in self._target_kinds:
            self._members = self._api.list_members()

        if EntityKind.GROUP in self._target_kinds:
            self._teams = self._api.list_teams()

        self._loading.set(False)

    def _filter_members(self) -> list[GitHubMember]:
        """Filter members by search query."""
        query = self._search_state.value().lower()
        if not query:
            return self._members
        return [m for m in self._members if query in m.login.lower()]

    def _filter_teams(self) -> list[GitHubTeam]:
        """Filter teams by search query."""
        query = self._search_state.value().lower()
        if not query:
            return self._teams
        return [
            team
            for team in self._teams
            if query in team.slug.lower() or query in (team.name or "").lower()
        ]

    def view(self):
        theme = ThemeManager().current

        # Load data on first render
        if not self._data_loaded:
            self._data_loaded = True
            self._do_load_data()

        if self._loading():
            return Column(
                Spacer().fixed_height(20),
                Text(t("github.loading"), font_size=14).text_color(theme.colors.fg),
                Spacer(),
            )

        if error := self._error():
            return Column(
                Spacer().fixed_height(20),
                Text(error, font_size=14).text_color(theme.colors.text_danger),
                Spacer().fixed_height(16),
                Button(t("common.close")).on_click(lambda _: self._on_close()),
                Spacer(),
            )

        # Build content based on target kinds
        content = [
            Input(self._search_state)
            .on_change(lambda _: self._render_trigger.set(self._render_trigger() + 1))
            .fixed_height(36),
            Spacer().fixed_height(8),
        ]

        # Show members if User is in target kinds
        show_members = EntityKind.USER in self._target_kinds and self._members
        show_teams = EntityKind.GROUP in self._target_kinds and self._teams

        if show_members and show_teams:
            # Both - split view
            content.extend(self._build_split_view())
        elif show_members:
            content.extend(self._build_members_section())
        elif show_teams:
            content.extend(self._build_teams_section())
        else:
            content.append(
                Text(t("status.no_entities"), font_size=14).text_color(theme.colors.fg)
            )

        return Column(*content).flex(1)

    def _build_split_view(self):
        """Build split view with members and teams."""
        theme = ThemeManager().current
        filtered_members = self._filter_members()
        filtered_teams = self._filter_teams()

        members_rows = [
            GitHubMemberRow(
                login=m.login,
                name=m.name or "",
            )
            for m in filtered_members[:30]
        ]

        teams_rows = [
            GitHubTeamRow(
                slug=team.slug,
                name=team.name,
                description=team.description or "",
            )
            for team in filtered_teams[:30]
        ]

        if members_rows:
            members_table_state = DataTableState.from_pydantic(members_rows)
        else:
            members_table_state = DataTableState(
                columns=[t("github.column.login"), t("github.column.name")], rows=[]
            )

        if teams_rows:
            teams_table_state = DataTableState.from_pydantic(teams_rows)
        else:
            teams_table_state = DataTableState(
                columns=[
                    t("github.column.slug"),
                    t("github.column.name"),
                    t("github.column.description"),
                ],
                rows=[],
            )

        def on_member_click(event):
            if 0 <= event.row < len(filtered_members):
                member = filtered_members[event.row]
                self._on_select(
                    {
                        "type": "user",
                        "login": member.login,
                        "name": member.name,
                        "email": member.email,
                        "avatar_url": member.avatar_url,
                    }
                )

        def on_team_click(event):
            if 0 <= event.row < len(filtered_teams):
                team = filtered_teams[event.row]
                self._on_select(
                    {
                        "type": "group",
                        "slug": team.slug,
                        "name": team.name,
                        "description": team.description,
                    }
                )

        return [
            Row(
                Column(
                    Text(
                        t("github.members_count", count=len(filtered_members)),
                        font_size=12,
                    )
                    .text_color(theme.colors.fg)
                    .fixed_height(20),
                    DataTable(members_table_state)
                    .on_cell_click(on_member_click)
                    .flex(1),
                ).flex(1),
                Spacer().fixed_width(8),
                Column(
                    Text(
                        t("github.teams_count", count=len(filtered_teams)),
                        font_size=12,
                    )
                    .text_color(theme.colors.fg)
                    .fixed_height(20),
                    DataTable(teams_table_state).on_cell_click(on_team_click).flex(1),
                ).flex(1),
            ).flex(1)
        ]

    def _build_members_section(self):
        """Build members-only section."""
        theme = ThemeManager().current
        filtered = self._filter_members()

        rows = [
            GitHubMemberRow(
                login=m.login,
                name=m.name or "",
            )
            for m in filtered[:50]
        ]

        if rows:
            table_state = DataTableState.from_pydantic(rows)
        else:
            table_state = DataTableState(
                columns=[t("github.column.login"), t("github.column.name")], rows=[]
            )

        def on_member_click(event):
            if 0 <= event.row < len(filtered):
                member = filtered[event.row]
                self._on_select(
                    {
                        "type": "user",
                        "login": member.login,
                        "name": member.name,
                        "email": member.email,
                        "avatar_url": member.avatar_url,
                    }
                )

        return [
            Text(t("github.members_count", count=len(filtered)), font_size=12)
            .text_color(theme.colors.fg)
            .fixed_height(20),
            DataTable(table_state).on_cell_click(on_member_click).flex(1),
        ]

    def _build_teams_section(self):
        """Build teams-only section."""
        theme = ThemeManager().current
        filtered = self._filter_teams()

        rows = [
            GitHubTeamRow(
                slug=team.slug,
                name=team.name,
                description=team.description or "",
            )
            for team in filtered[:50]
        ]

        if rows:
            table_state = DataTableState.from_pydantic(rows)
        else:
            table_state = DataTableState(
                columns=[
                    t("github.column.slug"),
                    t("github.column.name"),
                    t("github.column.description"),
                ],
                rows=[],
            )

        def on_team_click(event):
            if 0 <= event.row < len(filtered):
                team = filtered[event.row]
                self._on_select(
                    {
                        "type": "group",
                        "slug": team.slug,
                        "name": team.name,
                        "description": team.description,
                    }
                )

        return [
            Text(t("github.teams_count", count=len(filtered)), font_size=12)
            .text_color(theme.colors.fg)
            .fixed_height(20),
            DataTable(table_state).on_cell_click(on_team_click).flex(1),
        ]
