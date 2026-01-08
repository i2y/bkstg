"""Form-based entity editor component."""

from pathlib import Path
from typing import Callable

import yaml

from castella import (
    Box,
    Button,
    Column,
    Component,
    Input,
    InputState,
    Modal,
    ModalState,
    MultilineInput,
    MultilineInputState,
    Row,
    Spacer,
    State,
    Text,
)
from castella.theme import ThemeManager

from ..i18n import t
from ..models import Entity
from ..models.base import EntityKind, EntityLink, ScoreValue
from ..state.catalog_state import CatalogState
from .entity_templates import ENTITY_FIELD_CONFIGS, get_default_template
from castella import RadioButtonsState
from .form_fields import TextField, TextAreaField, SelectField, TagEditor, ButtonSelect, ButtonSelectState
from .reference_picker import ReferencePicker, MultiReferencePicker, EntityPickerModal


class FormEditor(Component):
    """Form-based entity editor."""

    KINDS = [
        EntityKind.COMPONENT,
        EntityKind.API,
        EntityKind.RESOURCE,
        EntityKind.SYSTEM,
        EntityKind.DOMAIN,
        EntityKind.USER,
        EntityKind.GROUP,
    ]

    def __init__(
        self,
        entity: Entity | None,
        file_path: Path | None,
        catalog_state: CatalogState,
        on_save: Callable[[Entity], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._entity = entity
        self._file_path = file_path
        self._catalog_state = catalog_state
        self._on_save = on_save
        self._on_cancel = on_cancel

        # Is this a new entity?
        self._is_new = entity is None

        # Kind selection (only for new entities)
        initial_kind_index = 0
        if entity:
            try:
                initial_kind_index = self.KINDS.index(entity.kind)
            except ValueError:
                initial_kind_index = 0

        self._kind_state = ButtonSelectState(
            [k.value for k in self.KINDS],
            initial_kind_index,
        )
        self._kind_state.attach(self)

        # Initialize form data from entity or template
        self._init_form_data()

        # Error state
        self._error = State("")
        self._error.attach(self)

        # Tab state
        self._active_tab = State("metadata")
        self._active_tab.attach(self)

        # Trigger re-render state
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        # Shared Modal for entity picking
        self._modal_state = ModalState()
        self._modal_state.attach(self)
        self._entity_picker_modal = EntityPickerModal(catalog_state)
        self._entity_picker_modal.attach(self)

        # Track current picker context
        self._current_picker_field: str | None = None
        self._current_picker_is_multi: bool = False

        # Score editing states: {score_id: (value_state, reason_state)}
        self._score_states: dict[str, tuple[InputState, InputState]] = {}
        self._init_score_states()

    def _init_score_states(self):
        """Initialize score editing states."""
        if not self._entity:
            return

        # Get score definitions
        score_defs = self._catalog_state.get_score_definitions()

        # Create states for existing scores
        for score in self._entity.metadata.scores:
            value_state = InputState(str(score.value))
            reason_state = InputState(score.reason or "")
            value_state.attach(self)
            reason_state.attach(self)
            self._score_states[score.score_id] = (value_state, reason_state)

        # Create states for score definitions not yet on this entity
        existing_ids = {s.score_id for s in self._entity.metadata.scores}
        for score_def in score_defs:
            score_id = score_def.get("id", "")
            if score_id and score_id not in existing_ids:
                value_state = InputState("")
                reason_state = InputState("")
                value_state.attach(self)
                reason_state.attach(self)
                self._score_states[score_id] = (value_state, reason_state)

    def _trigger_render(self):
        """Trigger a re-render by updating the render trigger state."""
        self._render_trigger.set(self._render_trigger() + 1)

    def _init_form_data(self):
        """Initialize form data from entity or template."""
        if self._entity:
            # Load from existing entity
            self._form_data = {
                "name": self._entity.metadata.name,
                "namespace": self._entity.metadata.namespace or "default",
                "title": self._entity.metadata.title or "",
                "description": self._entity.metadata.description or "",
                "tags": list(self._entity.metadata.tags or []),
                "links": [
                    {"url": link.url, "title": link.title or ""}
                    for link in (self._entity.metadata.links or [])
                ],
            }
            # Load spec fields
            if hasattr(self._entity, "spec") and self._entity.spec:
                spec = self._entity.spec
                for field in ["type", "lifecycle", "owner", "system", "domain"]:
                    if hasattr(spec, field):
                        self._form_data[field] = getattr(spec, field) or ""
                # Handle array fields
                for field in [
                    "providesApis",
                    "consumesApis",
                    "dependsOn",
                    "dependencyOf",
                    "memberOf",
                    "members",
                ]:
                    if hasattr(spec, field):
                        val = getattr(spec, field)
                        self._form_data[field] = list(val) if val else []
                # Handle special fields
                if hasattr(spec, "definition"):
                    self._form_data["definition"] = spec.definition or ""
                if hasattr(spec, "subcomponentOf"):
                    self._form_data["subcomponentOf"] = spec.subcomponentOf or ""
                if hasattr(spec, "subdomainOf"):
                    self._form_data["subdomainOf"] = spec.subdomainOf or ""
                if hasattr(spec, "parent"):
                    self._form_data["parent"] = spec.parent or ""
                # Handle profile
                if hasattr(spec, "profile") and spec.profile:
                    if hasattr(spec.profile, "displayName"):
                        self._form_data["displayName"] = spec.profile.displayName or ""
                    if hasattr(spec.profile, "email"):
                        self._form_data["email"] = spec.profile.email or ""
        else:
            # Load from template
            template = get_default_template(self._get_current_kind())
            self._form_data = {
                "name": template["metadata"]["name"],
                "namespace": "default",
                "title": "",
                "description": template["metadata"].get("description", ""),
                "tags": list(template["metadata"].get("tags", [])),
                "links": [],
            }
            spec = template.get("spec", {})
            for key, value in spec.items():
                if key == "profile":
                    self._form_data["displayName"] = value.get("displayName", "")
                    self._form_data["email"] = value.get("email", "")
                else:
                    self._form_data[key] = value if value else ""

        # Create input states
        self._name_state = InputState(self._form_data.get("name", ""))
        self._namespace_state = InputState(self._form_data.get("namespace", "default"))
        self._title_state = InputState(self._form_data.get("title", ""))
        self._description_state = MultilineInputState(
            self._form_data.get("description", "")
        )

        # Attach states
        for state in [
            self._name_state,
            self._namespace_state,
            self._title_state,
            self._description_state,
        ]:
            state.attach(self)

    def _get_current_kind(self) -> EntityKind:
        """Get currently selected entity kind."""
        if self._entity:
            return self._entity.kind
        return self.KINDS[self._kind_state.selected_index()]

    def view(self):
        theme = ThemeManager().current
        current_kind = self._get_current_kind()
        error_text = self._error()
        active_tab = self._active_tab()

        # Build header title
        header_title = (
            t("form.edit_entity", kind=current_kind.value)
            if self._entity
            else t("form.new_entity", kind=current_kind.value)
        )
        main_content = Column(
            # Header
            Row(
                Text(header_title, font_size=20).flex(1),
                Button(t("common.save")).on_click(self._handle_save).fixed_width(80),
                Spacer().fixed_width(8),
                Button(t("common.cancel")).on_click(lambda _: self._on_cancel()).fixed_width(80),
            ).fixed_height(44),
            Spacer().fixed_height(8),
            # Kind selector (only for new entities)
            (
                self._build_kind_selector()
                if self._is_new
                else Spacer().fixed_height(0)
            ),
            Spacer().fixed_height(8),
            # Tab buttons
            Row(
                Button(t("form.tab.metadata"))
                .on_click(lambda _: self._active_tab.set("metadata"))
                .bg_color(theme.colors.bg_selected if active_tab == "metadata" else theme.colors.bg_secondary)
                .fixed_height(36),
                Spacer().fixed_width(8),
                Button(t("form.tab.spec"))
                .on_click(lambda _: self._active_tab.set("spec"))
                .bg_color(theme.colors.bg_selected if active_tab == "spec" else theme.colors.bg_secondary)
                .fixed_height(36),
                Spacer().fixed_width(8),
                Button(t("form.tab.scores"))
                .on_click(lambda _: self._active_tab.set("scores"))
                .bg_color(theme.colors.bg_selected if active_tab == "scores" else theme.colors.bg_secondary)
                .fixed_height(36),
                Spacer(),
            ).fixed_height(44),
            Spacer().fixed_height(8),
            # Form content based on selected tab - fills remaining space
            self._build_tab_content(active_tab, current_kind),
            # Error display
            (
                Text(error_text, font_size=12).text_color(theme.colors.text_danger).fixed_height(24)
                if error_text
                else Spacer().fixed_height(0)
            ),
        ).flex(1)

        # Always use Box - Modal handles its own visibility
        modal_content = self._entity_picker_modal.build_content(self._close_picker)
        modal = Modal(
            content=modal_content,
            state=self._modal_state,
            title=t("form.select_entity"),
            width=600,
            height=500,
        )
        return Box(main_content, modal)

    def _build_kind_selector(self):
        """Build kind selector for new entities."""
        theme = ThemeManager().current
        return Column(
            Text(t("form.label.kind"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            ButtonSelect(self._kind_state),
            Spacer().fixed_height(8),
        ).fixed_height(68)

    def _build_tab_content(self, active_tab: str, current_kind: EntityKind):
        """Build content for the active tab."""
        if active_tab == "metadata":
            return self._build_metadata_section()
        elif active_tab == "spec":
            return self._build_spec_section(current_kind)
        elif active_tab == "scores":
            return self._build_scores_section()
        return Spacer()

    def _build_metadata_section(self):
        """Build metadata form fields."""
        theme = ThemeManager().current
        return Column(
            TextField(t("entity.field.name"), self._name_state, required=True),
            TextField(t("entity.field.namespace"), self._namespace_state),
            TextField(t("entity.field.title"), self._title_state),
            # Description expands to fill remaining space
            Column(
                Text(t("entity.field.description"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                MultilineInput(self._description_state, font_size=13).fit_parent(),
            ).flex(1),
            TagEditor(
                t("entity.field.tags"),
                self._form_data.get("tags", []),
                self._on_tags_change,
            ),
            # Links section
            self._build_links_editor(),
        ).flex(1)

    def _build_links_editor(self):
        """Build links editor section."""
        theme = ThemeManager().current
        links = self._form_data.get("links", [])

        items = [
            Text(t("entity.field.links"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
        ]

        # Existing links
        for i, link in enumerate(links):
            items.append(
                Row(
                    Text(t("form.link_title"), font_size=11).fixed_width(40),
                    Input(InputState(link.get("title", "")))
                    .on_change(lambda v, idx=i: self._on_link_title_change(idx, v))
                    .fixed_width(100),
                    Spacer().fixed_width(8),
                    Text(t("form.link_url"), font_size=11).fixed_width(30),
                    Input(InputState(link.get("url", "")))
                    .on_change(lambda v, idx=i: self._on_link_url_change(idx, v))
                    .flex(1),
                    Spacer().fixed_width(8),
                    Button(t("common.x"))
                    .on_click(lambda _, idx=i: self._on_link_remove(idx))
                    .fixed_width(32),
                ).fixed_height(36)
            )

        # Add link button
        items.append(
            Row(
                Button(t("form.add_link")).on_click(self._on_link_add),
                Spacer(),
            ).fixed_height(36)
        )

        return Column(*items)

    def _on_link_title_change(self, index: int, value: str):
        """Handle link title change."""
        links = self._form_data.get("links", [])
        if 0 <= index < len(links):
            links[index]["title"] = value

    def _on_link_url_change(self, index: int, value: str):
        """Handle link URL change."""
        links = self._form_data.get("links", [])
        if 0 <= index < len(links):
            links[index]["url"] = value

    def _on_link_remove(self, index: int):
        """Handle link removal."""
        links = self._form_data.get("links", [])
        if 0 <= index < len(links):
            links.pop(index)
            self._trigger_render()

    def _on_link_add(self, _):
        """Handle adding a new link."""
        links = self._form_data.get("links", [])
        links.append({"url": "", "title": ""})
        self._trigger_render()

    def _build_spec_section(self, kind: EntityKind):
        """Build kind-specific spec form fields."""
        field_configs = ENTITY_FIELD_CONFIGS.get(kind, [])
        fields = []
        select_fields = []  # Collect select fields to arrange in a Row

        for config in field_configs:
            if config.field_type == "text":
                state = InputState(str(self._form_data.get(config.name, "")))
                state.attach(self)
                fields.append(
                    TextField(
                        config.label,
                        state,
                        config.required,
                        config.placeholder,
                    )
                )
                # Store for later retrieval
                setattr(self, f"_spec_{config.name}_state", state)

            elif config.field_type == "textarea":
                state = MultilineInputState(str(self._form_data.get(config.name, "")))
                state.attach(self)
                fields.append(
                    TextAreaField(
                        config.label,
                        state,
                        config.required,
                        height=200,
                    )
                )
                setattr(self, f"_spec_{config.name}_state", state)

            elif config.field_type == "select" and config.options:
                options = config.options
                state_attr = f"_spec_{config.name}_state"
                # Reuse existing state if available
                if hasattr(self, state_attr):
                    state = getattr(self, state_attr)
                else:
                    current_value = str(self._form_data.get(config.name, ""))
                    try:
                        selected_index = options.index(current_value)
                    except ValueError:
                        selected_index = 0
                    # Create RadioButtonsState
                    state = RadioButtonsState(options, selected_index)
                    state.attach(self)
                    setattr(self, state_attr, state)
                    # Store field name for on_change lookup
                    setattr(self, f"_spec_{config.name}_options", options)
                select_fields.append(
                    SelectField(
                        config.label,
                        options,
                        state,
                        config.required,
                    )
                )

            elif config.field_type == "reference" and config.target_kinds:
                current_value = str(self._form_data.get(config.name, ""))
                picker = ReferencePicker(
                    config.label,
                    config.target_kinds,
                    self._catalog_state,
                    current_value,
                    lambda v, n=config.name: self._on_reference_change(n, v),
                    lambda n=config.name, tk=config.target_kinds: self._open_picker(n, tk, is_multi=False),
                    config.required,
                )
                fields.append(picker)

            elif config.field_type == "multi_reference" and config.target_kinds:
                current_values = self._form_data.get(config.name, [])
                if not isinstance(current_values, list):
                    current_values = []
                picker = MultiReferencePicker(
                    config.label,
                    config.target_kinds,
                    self._catalog_state,
                    current_values,
                    lambda v, n=config.name: self._on_multi_reference_change(n, v),
                    lambda n=config.name, tk=config.target_kinds: self._open_picker(n, tk, is_multi=True, exclude_ids=self._form_data.get(n, [])),
                )
                fields.append(picker)

        # Add select fields in a Row (Type and Lifecycle side by side)
        if select_fields:
            # Fixed height to ensure all radio options are visible
            fields.insert(0, Row(*select_fields, Spacer()).fixed_height(130))

        if not fields and not select_fields:
            theme = ThemeManager().current
            fields.append(
                Text(t("entity.no_spec_fields"), font_size=13)
                .text_color(theme.colors.fg)
                .fixed_height(40)
            )

        # Add spacer at end to push content to top
        fields.append(Spacer().flex(1))

        return Column(*fields).flex(1)

    def _build_scores_section(self):
        """Build scores editing section."""
        theme = ThemeManager().current

        if not self._entity:
            return Column(
                Text(t("scorecard.save_first"), font_size=13)
                .text_color(theme.colors.fg)
                .fixed_height(40),
                Spacer(),
            ).flex(1)

        # Get score definitions
        score_defs = self._catalog_state.get_score_definitions()

        if not score_defs:
            return Column(
                Text(t("scorecard.no_score_definitions"), font_size=13)
                .text_color(theme.colors.fg)
                .fixed_height(40),
                Text(t("scorecard.create_definitions_hint"), font_size=12)
                .text_color(theme.colors.border_primary)
                .fixed_height(24),
                Spacer(),
            ).flex(1)

        # Build score rows
        rows = []
        for score_def in score_defs:
            score_id = score_def.get("id", "")
            score_name = score_def.get("name", score_id)
            min_val = score_def.get("min_value", 0)
            max_val = score_def.get("max_value", 100)

            if score_id not in self._score_states:
                continue

            value_state, reason_state = self._score_states[score_id]

            rows.append(
                Column(
                    Text(score_name, font_size=14).fixed_height(24),
                    Row(
                        Column(
                            Text(t("scorecard.value_range", min=min_val, max=max_val), font_size=11)
                            .text_color(theme.colors.fg)
                            .fixed_height(18),
                            Input(value_state).fixed_height(32),
                        ).fixed_width(100),
                        Spacer().fixed_width(16),
                        Column(
                            Text(t("scorecard.reason"), font_size=11)
                            .text_color(theme.colors.fg)
                            .fixed_height(18),
                            Input(reason_state).fixed_height(32),
                        ).flex(1),
                    ).fixed_height(56),
                    Spacer().fixed_height(8),
                ).fixed_height(90)
            )

        # Add bottom padding
        rows.append(Spacer().fixed_height(16))
        return Column(*rows, scrollable=True).flex(1)

    def _on_tags_change(self, tags: list[str]):
        """Handle tag change."""
        self._form_data["tags"] = tags
        self._trigger_render()

    def _on_select_change(self, field_name: str, value: str):
        """Handle select field change."""
        self._form_data[field_name] = value

    def _on_reference_change(self, field_name: str, value: str):
        """Handle reference field change."""
        self._form_data[field_name] = value
        self._trigger_render()

    def _on_multi_reference_change(self, field_name: str, values: list[str]):
        """Handle multi-reference field change (called from picker's remove)."""
        self._form_data[field_name] = values
        # Don't call _trigger_render here - the picker already does it

    def _open_picker(
        self,
        field_name: str,
        target_kinds: list[EntityKind],
        is_multi: bool = False,
        exclude_ids: list[str] | None = None,
    ):
        """Open the entity picker modal."""
        self._current_picker_field = field_name
        self._current_picker_is_multi = is_multi
        self._entity_picker_modal.configure(
            target_kinds=target_kinds,
            exclude_ids=exclude_ids,
            on_select=self._on_picker_select,
        )
        self._modal_state.open()

    def _on_picker_select(self, entity_id: str):
        """Handle entity selection from picker."""
        if self._current_picker_field is None:
            return

        if self._current_picker_is_multi:
            # Add to list in form_data
            current = self._form_data.get(self._current_picker_field, [])
            if not isinstance(current, list):
                current = []
            if entity_id and entity_id not in current:
                current.append(entity_id)
                self._form_data[self._current_picker_field] = current
        else:
            # Single selection
            self._form_data[self._current_picker_field] = entity_id
        # Note: _trigger_render is called in _close_picker after modal closes

    def _close_picker(self):
        """Close the picker modal and trigger re-render."""
        self._current_picker_field = None
        # Close modal FIRST, then trigger re-render
        self._modal_state.close()
        self._trigger_render()

    def _handle_save(self, _):
        """Validate and save the entity."""
        # Update form data from states
        self._form_data["name"] = self._name_state.value()
        self._form_data["namespace"] = self._namespace_state.value() or "default"
        self._form_data["title"] = self._title_state.value()
        self._form_data["description"] = self._description_state.value()

        # Update spec fields from states
        current_kind = self._get_current_kind()
        field_configs = ENTITY_FIELD_CONFIGS.get(current_kind, [])

        for config in field_configs:
            state_attr = f"_spec_{config.name}_state"
            if hasattr(self, state_attr):
                state = getattr(self, state_attr)
                if config.field_type == "select":
                    options = config.options or []
                    if options:
                        self._form_data[config.name] = options[state.selected_index()]
                elif hasattr(state, "value"):
                    self._form_data[config.name] = state.value()

        # Validate
        errors = self._validate()
        if errors:
            self._error.set("\n".join(errors))
            return

        # Build entity dict
        try:
            entity_dict = self._build_entity_dict()
            # Parse and validate via Pydantic
            from ..git import EntityReader

            reader = EntityReader()
            entity = reader.parse_entity(entity_dict)

            if entity:
                # Record score history for changed scores (before save)
                scores_changed = self._check_and_record_score_history(entity)
                # Save entity (triggers reload, which computes ranks)
                self._on_save(entity)
                # Record rank history after save (ranks are now computed)
                if scores_changed:
                    self._record_rank_history_after_save(entity)
            else:
                self._error.set(t("validation.failed_to_create"))
        except Exception as e:
            self._error.set(t("validation.error", message=str(e)))

    def _check_and_record_score_history(self, entity: Entity) -> bool:
        """Record history for scores that changed.

        Returns:
            True if any scores changed, False otherwise.
        """
        if not self._entity:
            # New entity - no history to record
            return False

        entity_id = entity.entity_id
        old_scores = {s.score_id: s for s in self._entity.metadata.scores}
        scores_changed = False

        for score in entity.metadata.scores:
            old_score = old_scores.get(score.score_id)
            if old_score is None or old_score.value != score.value or old_score.reason != score.reason:
                # Score changed or is new - record history
                self._catalog_state.record_score_history(
                    entity_id=entity_id,
                    score_id=score.score_id,
                    value=score.value,
                    reason=score.reason,
                    source="ui",
                )
                scores_changed = True

        return scores_changed

    def _record_rank_history_after_save(self, entity: Entity):
        """Record rank history after scores are saved.

        This is called after _on_save() completes (which triggers reload()),
        so ranks have been computed and are available in the catalog state.
        """
        if not self._catalog_state:
            return

        entity_id = entity.entity_id

        # Get computed ranks from catalog state (calculated during reload)
        ranks = self._catalog_state.get_entity_ranks(entity_id)

        # Get current scores for snapshot
        current_scores = {s.score_id: s.value for s in entity.metadata.scores}

        for rank in ranks:
            rank_id = rank.get("rank_id")
            value = rank.get("value")
            label = rank.get("label")

            if rank_id and value is not None:
                self._catalog_state.record_rank_history(
                    entity_id=entity_id,
                    rank_id=rank_id,
                    value=value,
                    label=label,
                    score_snapshot=current_scores,
                )

    def _validate(self) -> list[str]:
        """Validate form data and return list of errors."""
        errors = []

        # Validate name
        name = self._form_data.get("name", "").strip()
        if not name:
            errors.append(t("validation.required", field=t("entity.field.name")))
        elif not all(c.isalnum() or c in "-_" for c in name):
            errors.append(t("validation.invalid_name"))

        # Validate required spec fields
        current_kind = self._get_current_kind()
        field_configs = ENTITY_FIELD_CONFIGS.get(current_kind, [])

        for config in field_configs:
            if config.required:
                value = self._form_data.get(config.name)
                if config.field_type == "multi_reference":
                    if not value or len(value) == 0:
                        errors.append(t("validation.required", field=config.label))
                elif not value:
                    errors.append(t("validation.required", field=config.label))

        return errors

    def _build_entity_dict(self) -> dict:
        """Build entity dictionary from form data."""
        current_kind = self._get_current_kind()

        entity_dict = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": current_kind.value,
            "metadata": {
                "name": self._form_data.get("name", ""),
                "namespace": self._form_data.get("namespace", "default"),
            },
            "spec": {},
        }

        # Add optional metadata
        if self._form_data.get("title"):
            entity_dict["metadata"]["title"] = self._form_data["title"]
        if self._form_data.get("description"):
            entity_dict["metadata"]["description"] = self._form_data["description"]
        if self._form_data.get("tags"):
            entity_dict["metadata"]["tags"] = self._form_data["tags"]
        # Add links (Backstage standard format)
        links = self._form_data.get("links", [])
        if links:
            entity_dict["metadata"]["links"] = [
                {"url": link["url"], "title": link["title"]}
                if link.get("title")
                else {"url": link["url"]}
                for link in links
                if link.get("url")  # Only include links with URLs
            ]

        # Add scores from score states
        scores = []
        for score_id, (value_state, reason_state) in self._score_states.items():
            value_str = value_state.value().strip()
            if value_str:  # Only include scores with values
                try:
                    value = float(value_str)
                    score_entry = {"score_id": score_id, "value": value}
                    reason = reason_state.value().strip()
                    if reason:
                        score_entry["reason"] = reason
                    scores.append(score_entry)
                except ValueError:
                    pass  # Skip invalid values
        if scores:
            entity_dict["metadata"]["scores"] = scores

        # Build spec based on kind
        field_configs = ENTITY_FIELD_CONFIGS.get(current_kind, [])

        for config in field_configs:
            value = self._form_data.get(config.name)
            if value:
                # Handle profile fields specially for User/Group
                if config.name in ["displayName", "email"]:
                    if "profile" not in entity_dict["spec"]:
                        entity_dict["spec"]["profile"] = {}
                    entity_dict["spec"]["profile"][config.name] = value
                else:
                    entity_dict["spec"][config.name] = value

        return entity_dict
