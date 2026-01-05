"""YAML editor component."""

from pathlib import Path

import yaml

from castella import (
    Button,
    Column,
    Component,
    MultilineInput,
    MultilineInputState,
    Row,
    Spacer,
    Text,
)

from ..git import EntityReader
from ..models import Entity


class YAMLEditor(Component):
    """YAML editor for entity files."""

    def __init__(
        self,
        entity: Entity | None,
        file_path: Path | None,
        on_save,
        on_cancel,
    ):
        super().__init__()
        self._entity = entity
        self._file_path = file_path
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._error = ""

        # Initialize text state
        if entity:
            yaml_str = yaml.dump(
                entity.model_dump(exclude_none=True),
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        else:
            yaml_str = self._get_template()

        self._text_state = MultilineInputState(yaml_str)

    def _get_template(self) -> str:
        """Get a template for new entity."""
        return """apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: my-component
  description: A new component
spec:
  type: service
  lifecycle: experimental
  owner: team-a
"""

    def view(self):
        title = (
            f"Editing: {self._entity.metadata.name}"
            if self._entity
            else "New Entity"
        )

        return Column(
            # Toolbar
            Row(
                Text(title, font_size=18).flex(1),
                Button("Save").on_click(self._handle_save).fixed_width(80),
                Spacer().fixed_width(8),
                Button("Cancel").on_click(lambda _: self._on_cancel()).fixed_width(80),
            ).fixed_height(44),
            # File path
            Text(
                f"File: {self._file_path or 'New file'}", font_size=12
            ).fixed_height(24),
            # Error message
            self._build_error(),
            Spacer().fixed_height(8),
            # Editor
            MultilineInput(
                self._text_state,
                font_size=14,
            ),
        )

    def _build_error(self):
        if not self._error:
            return Spacer().fixed_height(0)

        return (
            Text(self._error, font_size=13)
            .text_color("#ff6b6b")
            .fixed_height(28)
        )

    def _handle_save(self, _):
        try:
            # Parse YAML
            text = self._text_state.value()
            data = yaml.safe_load(text)

            # Validate against model
            reader = EntityReader()
            entity = reader.parse_entity(data)

            if entity is None:
                self._error = "Error: Could not parse entity"
                return

            # Save
            self._error = ""
            self._on_save(entity)

        except yaml.YAMLError as e:
            self._error = f"YAML Error: {e}"
        except Exception as e:
            self._error = f"Error: {e}"
