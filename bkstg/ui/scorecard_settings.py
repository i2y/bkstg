"""Scorecard Settings UI for editing score and rank definitions."""

from typing import Any, Callable

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
from ..models.scorecard import (
    RankDefinition,
    RankThreshold,
    ScoreDefinition,
    ScorecardDefinition,
    ScorecardDefinitionMetadata,
    ScorecardDefinitionSpec,
)
from ..scorecard.evaluator import FormulaError, SafeFormulaEvaluator
from ..state.catalog_state import CatalogState


# Available entity kinds for target_kinds selection
ENTITY_KINDS = ["Component", "API", "Resource", "System", "Domain", "User", "Group"]


class ThresholdEditor(Component):
    """Editor for rank thresholds (dynamic list)."""

    def __init__(
        self,
        thresholds: list[dict],
        on_change: Callable[[list[dict]], None],
    ):
        super().__init__()
        self._thresholds = thresholds
        self._on_change = on_change

        self._min_state = InputState("")
        self._label_state = InputState("")
        self._render_trigger = State(0)

        self._min_state.attach(self)
        self._label_state.attach(self)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        items = []
        for i, th in enumerate(self._thresholds):
            items.append(
                Row(
                    Text(f"{th['min']}", font_size=12)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(60),
                    Text("->", font_size=12).text_color(theme.colors.fg).fixed_width(30),
                    Text(th["label"], font_size=12)
                    .text_color(theme.colors.text_success)
                    .fixed_width(60),
                    Spacer(),
                    Button("x")
                    .on_click(lambda _, idx=i: self._remove(idx))
                    .fixed_width(28)
                    .fixed_height(28),
                )
                .fixed_height(32)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(4))

        return Column(
            Text(t("scorecard.thresholds"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Column(*items, scrollable=True).fixed_height(140),
            Row(
                Input(self._min_state).fixed_width(80).fixed_height(32),
                Spacer().fixed_width(8),
                Text("->", font_size=12).text_color(theme.colors.fg).fixed_width(30),
                Spacer().fixed_width(8),
                Input(self._label_state).fixed_width(80).fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("common.add")).on_click(self._add).fixed_width(60).fixed_height(32),
            ).fixed_height(36),
        ).fixed_height(200)

    def _add(self, _):
        try:
            min_val = float(self._min_state.value())
            label = self._label_state.value().strip()
            if label:
                self._thresholds.append({"min": min_val, "label": label})
                self._thresholds.sort(key=lambda t: t["min"], reverse=True)
                self._min_state.set("")
                self._label_state.set("")
                self._on_change(self._thresholds)
                self._render_trigger.set(self._render_trigger() + 1)
        except ValueError:
            pass

    def _remove(self, index: int):
        if 0 <= index < len(self._thresholds):
            self._thresholds.pop(index)
            self._on_change(self._thresholds)
            self._render_trigger.set(self._render_trigger() + 1)


class FormulaField(Component):
    """Formula input with validation."""

    def __init__(
        self,
        label: str,
        formula_state: MultilineInputState,
        score_refs: list[str],
        on_validation_change: Callable[[bool, str], None],
    ):
        super().__init__()
        self._label = label
        self._formula_state = formula_state
        self._score_refs = score_refs
        self._on_validation_change = on_validation_change

        self._validation_status = State("")
        self._validation_status.attach(self)

        self._is_valid = State(True)
        self._is_valid.attach(self)

    def view(self):
        theme = ThemeManager().current
        status = self._validation_status()
        is_valid = self._is_valid()

        return Column(
            Text(f"{self._label} *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            MultilineInput(self._formula_state, font_size=13).fixed_height(60),
            Row(
                Button(t("common.validate")).on_click(self._validate).fixed_width(80).fixed_height(28),
                Spacer().fixed_width(16),
                Text(status, font_size=12).text_color(theme.colors.text_success if is_valid else theme.colors.text_danger),
                Spacer(),
            ).fixed_height(32),
        ).fixed_height(120)

    def _validate(self, _):
        formula = self._formula_state.value()
        try:
            SafeFormulaEvaluator(formula, self._score_refs)
            self._is_valid.set(True)
            self._validation_status.set("Valid")
            self._on_validation_change(True, "")
        except FormulaError as e:
            self._is_valid.set(False)
            self._validation_status.set(f"Error: {e}")
            self._on_validation_change(False, str(e))

    def update_score_refs(self, score_refs: list[str]):
        """Update the score_refs list for validation."""
        self._score_refs = score_refs


class KindSelector(Component):
    """Multi-select for entity kinds using buttons."""

    def __init__(
        self,
        label: str,
        selected: list[str],
        on_change: Callable[[list[str]], None],
    ):
        super().__init__()
        self._label = label
        self._selected = selected
        self._on_change = on_change
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        buttons = []
        for kind in ENTITY_KINDS:
            is_selected = kind in self._selected
            btn = (
                Button(kind)
                .on_click(lambda _, k=kind: self._toggle(k))
                .fixed_height(28)
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
            )
            buttons.append(btn)
            buttons.append(Spacer().fixed_width(4))

        return Column(
            Text(self._label, font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Row(*buttons).fixed_height(32),
            Spacer().fixed_height(4),
        ).fixed_height(60)

    def _toggle(self, kind: str):
        if kind in self._selected:
            self._selected.remove(kind)
        else:
            self._selected.append(kind)
        self._on_change(self._selected)
        self._render_trigger.set(self._render_trigger() + 1)


class ScoreRefSelector(Component):
    """Multi-select for score references using buttons."""

    def __init__(
        self,
        label: str,
        available_scores: list[str],
        selected: list[str],
        on_change: Callable[[list[str]], None],
    ):
        super().__init__()
        self._label = label
        self._available_scores = available_scores
        self._selected = selected
        self._on_change = on_change
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        buttons = []
        for score_id in self._available_scores:
            is_selected = score_id in self._selected
            btn = (
                Button(score_id)
                .on_click(lambda _, s=score_id: self._toggle(s))
                .fixed_height(28)
                .bg_color(theme.colors.text_success if is_selected else theme.colors.bg_secondary)
            )
            buttons.append(btn)
            buttons.append(Spacer().fixed_width(4))

        if not self._available_scores:
            buttons.append(
                Text(t("scorecard.no_scores_defined"), font_size=12).text_color(theme.colors.fg)
            )

        return Column(
            Text(f"{self._label} *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Row(*buttons).fixed_height(32),
            Spacer().fixed_height(4),
        ).fixed_height(60)

    def _toggle(self, score_id: str):
        if score_id in self._selected:
            self._selected.remove(score_id)
        else:
            self._selected.append(score_id)
        self._on_change(self._selected)
        self._render_trigger.set(self._render_trigger() + 1)


class ScoreDefinitionEditor(Component):
    """Editor for a single ScoreDefinition."""

    def __init__(
        self,
        score: dict | None,
        on_save: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._on_save = on_save
        self._on_cancel = on_cancel

        # Initialize form data
        if score:
            self._form_data = dict(score)
        else:
            self._form_data = {
                "id": "",
                "name": "",
                "description": "",
                "target_kinds": [],
                "min_value": 0.0,
                "max_value": 100.0,
            }

        # Form states
        self._id_state = InputState(self._form_data.get("id", ""))
        self._name_state = InputState(self._form_data.get("name", ""))
        self._description_state = MultilineInputState(
            self._form_data.get("description") or ""
        )
        self._min_state = InputState(str(self._form_data.get("min_value", 0)))
        self._max_state = InputState(str(self._form_data.get("max_value", 100)))

        self._id_state.attach(self)
        self._name_state.attach(self)
        self._description_state.attach(self)
        self._min_state.attach(self)
        self._max_state.attach(self)

        self._error = State("")
        self._error.attach(self)

        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        error_text = self._error()

        return Column(
            # ID
            Column(
                Text(t("scorecard.id") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                Input(self._id_state).fixed_height(36),
            ).fixed_height(60),
            # Name
            Column(
                Text(t("entity.field.name") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                Input(self._name_state).fixed_height(36),
            ).fixed_height(60),
            # Description
            Column(
                Text(t("entity.field.description"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                MultilineInput(self._description_state, font_size=13).fixed_height(60),
            ).fixed_height(84),
            # Target Kinds
            KindSelector(
                t("scorecard.target_kinds"),
                self._form_data.get("target_kinds", []),
                lambda kinds: self._form_data.update({"target_kinds": kinds}),
            ),
            # Min/Max values
            Row(
                Column(
                    Text(t("scorecard.min_value"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                    Input(self._min_state).fixed_height(36),
                ).fixed_width(100),
                Spacer().fixed_width(16),
                Column(
                    Text(t("scorecard.max_value"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                    Input(self._max_state).fixed_height(36),
                ).fixed_width(100),
                Spacer(),
            ).fixed_height(60),
            Spacer(),
            # Error message
            (
                Text(error_text, font_size=12).text_color(theme.colors.text_danger).fixed_height(24)
                if error_text
                else Spacer().fixed_height(0)
            ),
            # Buttons
            Row(
                Spacer(),
                Button(t("common.cancel")).on_click(lambda _: self._on_cancel()).fixed_width(80),
                Spacer().fixed_width(8),
                Button(t("common.save")).on_click(self._save).bg_color(theme.colors.text_success).fixed_width(80),
            ).fixed_height(40),
        )

    def _save(self, _):
        # Validate
        id_val = self._id_state.value().strip()
        name_val = self._name_state.value().strip()

        if not id_val:
            self._error.set(t("validation.required", field=t("scorecard.id")))
            return
        if not name_val:
            self._error.set(t("validation.required", field=t("entity.field.name")))
            return

        try:
            min_val = float(self._min_state.value())
            max_val = float(self._max_state.value())
        except ValueError:
            self._error.set(t("validation.invalid_number"))
            return

        result = {
            "id": id_val,
            "name": name_val,
            "description": self._description_state.value().strip() or None,
            "target_kinds": self._form_data.get("target_kinds", []),
            "min_value": min_val,
            "max_value": max_val,
        }
        self._on_save(result)


class RankDefinitionEditor(Component):
    """Editor for a single RankDefinition."""

    def __init__(
        self,
        rank: dict | None,
        available_scores: list[str],
        on_save: Callable[[dict], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__()
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._available_scores = available_scores

        # Initialize form data
        if rank:
            self._form_data = dict(rank)
            # Convert thresholds to list of dicts if needed
            if "thresholds" in self._form_data:
                self._form_data["thresholds"] = [
                    dict(t) if isinstance(t, dict) else {"min": t.min, "label": t.label}
                    for t in self._form_data["thresholds"]
                ]
        else:
            self._form_data = {
                "id": "",
                "name": "",
                "description": "",
                "target_kinds": [],
                "score_refs": [],
                "formula": "",
                "thresholds": [],
            }

        # Form states
        self._id_state = InputState(self._form_data.get("id", ""))
        self._name_state = InputState(self._form_data.get("name", ""))
        self._description_state = MultilineInputState(
            self._form_data.get("description") or ""
        )
        self._formula_state = MultilineInputState(self._form_data.get("formula", ""))

        self._id_state.attach(self)
        self._name_state.attach(self)
        self._description_state.attach(self)
        self._formula_state.attach(self)

        self._error = State("")
        self._error.attach(self)

        self._formula_valid = True
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        error_text = self._error()
        score_refs = self._form_data.get("score_refs", [])

        return Column(
            # ID
            Column(
                Text(t("scorecard.id") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                Input(self._id_state).fixed_height(36),
            ).fixed_height(60),
            # Name
            Column(
                Text(t("entity.field.name") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                Input(self._name_state).fixed_height(36),
            ).fixed_height(60),
            # Description
            Column(
                Text(t("entity.field.description"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                MultilineInput(self._description_state, font_size=13).fixed_height(40),
            ).fixed_height(64),
            # Target Kinds
            KindSelector(
                t("scorecard.target_kinds"),
                self._form_data.get("target_kinds", []),
                lambda kinds: self._form_data.update({"target_kinds": kinds}),
            ),
            # Score Refs
            ScoreRefSelector(
                t("scorecard.score_refs"),
                self._available_scores,
                score_refs,
                self._on_score_refs_change,
            ),
            # Formula
            FormulaField(
                t("scorecard.formula"),
                self._formula_state,
                score_refs,
                self._on_formula_validation,
            ),
            # Thresholds
            ThresholdEditor(
                self._form_data.get("thresholds", []),
                lambda th: self._form_data.update({"thresholds": th}),
            ),
            Spacer().fixed_height(16),
            # Error message
            (
                Text(error_text, font_size=12).text_color(theme.colors.text_danger).fixed_height(24)
                if error_text
                else Spacer().fixed_height(0)
            ),
            # Buttons
            Row(
                Spacer(),
                Button(t("common.cancel")).on_click(lambda _: self._on_cancel()).fixed_width(80),
                Spacer().fixed_width(8),
                Button(t("common.save")).on_click(self._save).bg_color(theme.colors.text_success).fixed_width(80),
            ).fixed_height(40),
        )

    def _on_score_refs_change(self, refs: list[str]):
        self._form_data["score_refs"] = refs
        self._render_trigger.set(self._render_trigger() + 1)

    def _on_formula_validation(self, is_valid: bool, error: str):
        self._formula_valid = is_valid

    def _save(self, _):
        # Validate
        id_val = self._id_state.value().strip()
        name_val = self._name_state.value().strip()
        formula = self._formula_state.value().strip()
        score_refs = self._form_data.get("score_refs", [])

        if not id_val:
            self._error.set(t("validation.required", field=t("scorecard.id")))
            return
        if not name_val:
            self._error.set(t("validation.required", field=t("entity.field.name")))
            return
        if not score_refs:
            self._error.set(t("validation.required", field=t("scorecard.score_refs")))
            return
        if not formula:
            self._error.set(t("validation.required", field=t("scorecard.formula")))
            return

        # Validate formula
        try:
            SafeFormulaEvaluator(formula, score_refs)
        except FormulaError as e:
            self._error.set(t("validation.error", message=str(e)))
            return

        result = {
            "id": id_val,
            "name": name_val,
            "description": self._description_state.value().strip() or None,
            "target_kinds": self._form_data.get("target_kinds", []),
            "score_refs": score_refs,
            "formula": formula,
            "thresholds": self._form_data.get("thresholds", []),
        }
        self._on_save(result)


class ScorecardSettingsTab(Component):
    """Settings tab for scorecard configuration."""

    def __init__(self, catalog_state: CatalogState):
        super().__init__()
        self._catalog_state = catalog_state

        # Section state
        self._active_section = State("scores")
        self._active_section.attach(self)

        # Dirty state
        self._is_dirty = State(False)
        self._is_dirty.attach(self)

        # Modal state
        self._modal_state = ModalState()
        self._modal_state.attach(self)

        # Editing state
        self._editing_type: str | None = None  # "score" or "rank"
        self._editing_index: int | None = None  # None = new

        # Status message
        self._status = State("")
        self._status.attach(self)

        # Render trigger
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

        # Load data
        self._score_definitions: list[dict] = []
        self._rank_definitions: list[dict] = []
        self._load_data()

    def _load_data(self):
        """Load definitions from catalog state."""
        self._score_definitions = [
            dict(d) for d in self._catalog_state.get_score_definitions()
        ]
        self._rank_definitions = [
            dict(d) for d in self._catalog_state.get_rank_definitions()
        ]

    def view(self):
        theme = ThemeManager().current
        section = self._active_section()
        is_dirty = self._is_dirty()
        status = self._status()

        main_content = Column(
            # Header with section tabs and save button
            Row(
                Button(t("scorecard.scores"))
                .on_click(lambda _: self._active_section.set("scores"))
                .bg_color(theme.colors.bg_selected if section == "scores" else theme.colors.bg_secondary)
                .fixed_height(36),
                Spacer().fixed_width(8),
                Button(t("scorecard.ranks"))
                .on_click(lambda _: self._active_section.set("ranks"))
                .bg_color(theme.colors.bg_selected if section == "ranks" else theme.colors.bg_secondary)
                .fixed_height(36),
                Spacer(),
                (
                    Text(status, font_size=12).text_color(theme.colors.text_success)
                    if status
                    else Spacer().fixed_width(0)
                ),
                Spacer().fixed_width(16),
                Button(t("common.save") + (" *" if is_dirty else ""))
                .on_click(self._save_yaml)
                .bg_color(theme.colors.text_success if is_dirty else theme.colors.bg_secondary)
                .fixed_height(36),
            ).fixed_height(44),
            Spacer().fixed_height(16),
            # Content
            (
                self._build_scores_section()
                if section == "scores"
                else self._build_ranks_section()
            ),
        ).flex(1)

        # Modal
        modal_content = self._build_modal_content()
        modal = Modal(
            content=modal_content,
            state=self._modal_state,
            title=(
                t("scorecard.edit_score")
                if self._editing_type == "score"
                else t("scorecard.edit_rank")
            ),
            width=600,
            height=850,
        )

        return Box(main_content, modal)

    def _build_scores_section(self):
        """Build scores list section."""
        theme = ThemeManager().current
        items = []
        for i, score in enumerate(self._score_definitions):
            items.append(
                Row(
                    Text(score.get("id", ""), font_size=14)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(150),
                    Text(score.get("name", ""), font_size=14)
                    .text_color(theme.colors.fg)
                    .flex(1),
                    Button(t("common.edit"))
                    .on_click(lambda _, idx=i: self._edit_score(idx))
                    .fixed_width(60)
                    .fixed_height(28),
                    Spacer().fixed_width(8),
                    Button(t("common.delete"))
                    .on_click(lambda _, idx=i: self._delete_score(idx))
                    .bg_color(theme.colors.text_danger)
                    .fixed_width(50)
                    .fixed_height(28),
                )
                .fixed_height(40)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(4))

        return Column(
            Row(
                Text(t("scorecard.score_definitions"), font_size=18).fixed_height(32),
                Spacer(),
                Button(t("common.add_item"))
                .on_click(lambda _: self._add_score())
                .bg_color(theme.colors.bg_selected)
                .fixed_height(32),
            ).fixed_height(40),
            Spacer().fixed_height(8),
            Column(*items, scrollable=True).flex(1),
        )

    def _build_ranks_section(self):
        """Build ranks list section."""
        theme = ThemeManager().current
        items = []
        for i, rank in enumerate(self._rank_definitions):
            items.append(
                Row(
                    Text(rank.get("id", ""), font_size=14)
                    .text_color(theme.colors.text_primary)
                    .fixed_width(150),
                    Text(rank.get("name", ""), font_size=14)
                    .text_color(theme.colors.fg)
                    .flex(1),
                    Button(t("common.edit"))
                    .on_click(lambda _, idx=i: self._edit_rank(idx))
                    .fixed_width(60)
                    .fixed_height(28),
                    Spacer().fixed_width(8),
                    Button(t("common.delete"))
                    .on_click(lambda _, idx=i: self._delete_rank(idx))
                    .bg_color(theme.colors.text_danger)
                    .fixed_width(50)
                    .fixed_height(28),
                )
                .fixed_height(40)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(4))

        return Column(
            Row(
                Text(t("scorecard.rank_definitions"), font_size=18).fixed_height(32),
                Spacer(),
                Button(t("common.add_item"))
                .on_click(lambda _: self._add_rank())
                .bg_color(theme.colors.bg_selected)
                .fixed_height(32),
            ).fixed_height(40),
            Spacer().fixed_height(8),
            Column(*items, scrollable=True).flex(1),
        )

    def _build_modal_content(self):
        """Build modal content based on editing state."""
        if self._editing_type == "score":
            score = (
                self._score_definitions[self._editing_index]
                if self._editing_index is not None
                else None
            )
            return ScoreDefinitionEditor(
                score,
                self._on_score_save,
                self._close_modal,
            )
        elif self._editing_type == "rank":
            rank = (
                self._rank_definitions[self._editing_index]
                if self._editing_index is not None
                else None
            )
            available_scores = [s.get("id", "") for s in self._score_definitions]
            return RankDefinitionEditor(
                rank,
                available_scores,
                self._on_rank_save,
                self._close_modal,
            )
        return Spacer()

    def _add_score(self):
        self._editing_type = "score"
        self._editing_index = None
        self._modal_state.open()

    def _edit_score(self, index: int):
        self._editing_type = "score"
        self._editing_index = index
        self._modal_state.open()

    def _delete_score(self, index: int):
        if 0 <= index < len(self._score_definitions):
            self._score_definitions.pop(index)
            self._is_dirty.set(True)
            self._render_trigger.set(self._render_trigger() + 1)

    def _add_rank(self):
        self._editing_type = "rank"
        self._editing_index = None
        self._modal_state.open()

    def _edit_rank(self, index: int):
        self._editing_type = "rank"
        self._editing_index = index
        self._modal_state.open()

    def _delete_rank(self, index: int):
        if 0 <= index < len(self._rank_definitions):
            self._rank_definitions.pop(index)
            self._is_dirty.set(True)
            self._render_trigger.set(self._render_trigger() + 1)

    def _on_score_save(self, score: dict):
        if self._editing_index is not None:
            self._score_definitions[self._editing_index] = score
        else:
            self._score_definitions.append(score)
        self._is_dirty.set(True)
        self._close_modal()

    def _on_rank_save(self, rank: dict):
        if self._editing_index is not None:
            self._rank_definitions[self._editing_index] = rank
        else:
            self._rank_definitions.append(rank)
        self._is_dirty.set(True)
        self._close_modal()

    def _close_modal(self):
        self._editing_type = None
        self._editing_index = None
        self._modal_state.close()
        self._render_trigger.set(self._render_trigger() + 1)

    def _save_yaml(self, _):
        """Save scorecard definition to YAML file."""
        try:
            # Get old definitions before saving (for history tracking)
            old_score_defs = {s["id"]: s for s in self._catalog_state.get_score_definitions()}
            old_rank_defs = {r["id"]: r for r in self._catalog_state.get_rank_definitions()}

            # Build ScoreDefinition objects
            scores = [
                ScoreDefinition(
                    id=s["id"],
                    name=s["name"],
                    description=s.get("description"),
                    target_kinds=s.get("target_kinds", []),
                    min_value=s.get("min_value", 0.0),
                    max_value=s.get("max_value", 100.0),
                )
                for s in self._score_definitions
            ]

            # Build RankDefinition objects
            ranks = [
                RankDefinition(
                    id=r["id"],
                    name=r["name"],
                    description=r.get("description"),
                    target_kinds=r.get("target_kinds", []),
                    score_refs=r.get("score_refs", []),
                    formula=r["formula"],
                    thresholds=[
                        RankThreshold(min=t["min"], label=t["label"])
                        for t in r.get("thresholds", [])
                    ],
                )
                for r in self._rank_definitions
            ]

            # Build ScorecardDefinition
            scorecard = ScorecardDefinition(
                metadata=ScorecardDefinitionMetadata(
                    name="tech-health",
                    title="Tech Health Scorecard",
                ),
                spec=ScorecardDefinitionSpec(
                    scores=scores,
                    ranks=ranks,
                ),
            )

            # Record definition changes before saving
            self._record_definition_changes(old_score_defs, old_rank_defs)

            # Save to file
            self._catalog_state.save_scorecard_definition(scorecard)

            # Reload data
            self._load_data()
            self._is_dirty.set(False)
            self._status.set(t("status.saved"))
            self._render_trigger.set(self._render_trigger() + 1)

        except Exception as e:
            self._status.set(t("validation.error", message=str(e)))
            self._render_trigger.set(self._render_trigger() + 1)

    def _record_definition_changes(
        self,
        old_score_defs: dict[str, dict],
        old_rank_defs: dict[str, dict],
    ) -> None:
        """Record definition changes to history."""
        new_score_defs = {s["id"]: s for s in self._score_definitions}
        new_rank_defs = {r["id"]: r for r in self._rank_definitions}

        # Check score definition changes
        all_score_ids = set(old_score_defs.keys()) | set(new_score_defs.keys())
        for score_id in all_score_ids:
            old_def = old_score_defs.get(score_id)
            new_def = new_score_defs.get(score_id)

            if old_def is None and new_def is not None:
                # Created
                self._catalog_state.record_definition_history(
                    definition_type="score",
                    definition_id=score_id,
                    change_type="created",
                    old_value=None,
                    new_value=new_def,
                    changed_fields=[],
                )
            elif old_def is not None and new_def is None:
                # Deleted
                self._catalog_state.record_definition_history(
                    definition_type="score",
                    definition_id=score_id,
                    change_type="deleted",
                    old_value=old_def,
                    new_value=None,
                    changed_fields=[],
                )
            elif old_def is not None and new_def is not None:
                # Check for updates
                changed_fields = self._get_changed_fields(old_def, new_def)
                if changed_fields:
                    self._catalog_state.record_definition_history(
                        definition_type="score",
                        definition_id=score_id,
                        change_type="updated",
                        old_value=old_def,
                        new_value=new_def,
                        changed_fields=changed_fields,
                    )

        # Check rank definition changes
        all_rank_ids = set(old_rank_defs.keys()) | set(new_rank_defs.keys())
        for rank_id in all_rank_ids:
            old_def = old_rank_defs.get(rank_id)
            new_def = new_rank_defs.get(rank_id)

            if old_def is None and new_def is not None:
                # Created
                self._catalog_state.record_definition_history(
                    definition_type="rank",
                    definition_id=rank_id,
                    change_type="created",
                    old_value=None,
                    new_value=new_def,
                    changed_fields=[],
                )
            elif old_def is not None and new_def is None:
                # Deleted
                self._catalog_state.record_definition_history(
                    definition_type="rank",
                    definition_id=rank_id,
                    change_type="deleted",
                    old_value=old_def,
                    new_value=None,
                    changed_fields=[],
                )
            elif old_def is not None and new_def is not None:
                # Check for updates
                changed_fields = self._get_changed_fields(old_def, new_def)
                if changed_fields:
                    self._catalog_state.record_definition_history(
                        definition_type="rank",
                        definition_id=rank_id,
                        change_type="updated",
                        old_value=old_def,
                        new_value=new_def,
                        changed_fields=changed_fields,
                    )

    def _get_changed_fields(self, old_def: dict, new_def: dict) -> list[str]:
        """Compare two definitions and return list of changed field names."""
        changed = []
        all_keys = set(old_def.keys()) | set(new_def.keys())
        for key in all_keys:
            if key in ("id",):  # Skip id field
                continue
            old_val = old_def.get(key)
            new_val = new_def.get(key)
            if old_val != new_val:
                changed.append(key)
        return changed
