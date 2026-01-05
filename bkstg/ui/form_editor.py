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

from ..models import Entity
from ..models.base import EntityKind
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
        current_kind = self._get_current_kind()
        error_text = self._error()
        active_tab = self._active_tab()

        main_content = Column(
            # Header
            Row(
                Text(
                    f"{'Edit' if self._entity else 'New'} {current_kind.value}",
                    font_size=20,
                ).flex(1),
                Button("Save").on_click(self._handle_save).fixed_width(80),
                Spacer().fixed_width(8),
                Button("Cancel").on_click(lambda _: self._on_cancel()).fixed_width(80),
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
                Button("Metadata")
                .on_click(lambda _: self._active_tab.set("metadata"))
                .bg_color("#3b82f6" if active_tab == "metadata" else "#374151")
                .fixed_height(36),
                Spacer().fixed_width(8),
                Button("Spec")
                .on_click(lambda _: self._active_tab.set("spec"))
                .bg_color("#3b82f6" if active_tab == "spec" else "#374151")
                .fixed_height(36),
                Spacer(),
            ).fixed_height(44),
            Spacer().fixed_height(8),
            # Form content based on selected tab - fills remaining space
            (
                self._build_metadata_section()
                if active_tab == "metadata"
                else self._build_spec_section(current_kind)
            ),
            # Error display
            (
                Text(error_text, font_size=12).text_color("#ef4444").fixed_height(24)
                if error_text
                else Spacer().fixed_height(0)
            ),
        ).flex(1)

        # Always use Box - Modal handles its own visibility
        modal_content = self._entity_picker_modal.build_content(self._close_picker)
        modal = Modal(
            content=modal_content,
            state=self._modal_state,
            title="Select Entity",
            width=600,
            height=500,
        )
        return Box(main_content, modal)

    def _build_kind_selector(self):
        """Build kind selector for new entities."""
        return Column(
            Text("Kind *", font_size=13).text_color("#d1d5db").fixed_height(20),
            ButtonSelect(self._kind_state),
            Spacer().fixed_height(8),
        ).fixed_height(68)

    def _build_metadata_section(self):
        """Build metadata form fields."""
        return Column(
            TextField("Name", self._name_state, required=True),
            TextField("Namespace", self._namespace_state),
            TextField("Title", self._title_state),
            # Description expands to fill remaining space
            Column(
                Text("Description", font_size=13).text_color("#d1d5db").fixed_height(20),
                MultilineInput(self._description_state, font_size=13).fit_parent(),
            ).flex(1),
            TagEditor(
                "Tags",
                self._form_data.get("tags", []),
                self._on_tags_change,
            ),
        ).flex(1)

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
            fields.append(
                Text("No spec fields for this entity kind", font_size=13)
                .text_color("#9ca3af")
                .fixed_height(40)
            )

        # Add spacer at end to push content to top
        fields.append(Spacer().flex(1))

        return Column(*fields).flex(1)

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
                self._on_save(entity)
            else:
                self._error.set("Failed to create entity: validation error")
        except Exception as e:
            self._error.set(f"Error: {e}")

    def _validate(self) -> list[str]:
        """Validate form data and return list of errors."""
        errors = []

        # Validate name
        name = self._form_data.get("name", "").strip()
        if not name:
            errors.append("Name is required")
        elif not all(c.isalnum() or c in "-_" for c in name):
            errors.append("Name must contain only alphanumeric characters, hyphens, and underscores")

        # Validate required spec fields
        current_kind = self._get_current_kind()
        field_configs = ENTITY_FIELD_CONFIGS.get(current_kind, [])

        for config in field_configs:
            if config.required:
                value = self._form_data.get(config.name)
                if config.field_type == "multi_reference":
                    if not value or len(value) == 0:
                        errors.append(f"{config.label} is required")
                elif not value:
                    errors.append(f"{config.label} is required")

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
