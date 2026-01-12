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
    RankRule,
    RankThreshold,
    ScoreDefinition,
    ScorecardDefinition,
    ScorecardDefinitionMetadata,
    ScorecardDefinitionSpec,
)
from ..scorecard.evaluator import (
    ConditionalRankEvaluator,
    FormulaError,
    LabelFunctionEvaluator,
    SafeFormulaEvaluator,
)
from ..state.catalog_state import CatalogState


# Available entity kinds for target_kinds selection
ENTITY_KINDS = ["Component", "API", "Resource", "System", "Domain", "User", "Group"]

# Available entity attributes for entity_refs
ENTITY_ATTRS = ["kind", "type", "lifecycle", "owner", "system", "domain", "namespace", "name", "tags"]

# Rank definition modes
RANK_MODE_SIMPLE = "simple"
RANK_MODE_CONDITIONAL = "conditional"
RANK_MODE_LABEL_FUNCTION = "label_function"


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


class EntityRefSelector(Component):
    """Multi-select for entity attributes using buttons."""

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
        for attr in ENTITY_ATTRS:
            is_selected = attr in self._selected
            btn = (
                Button(attr)
                .on_click(lambda _, a=attr: self._toggle(a))
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

    def _toggle(self, attr: str):
        if attr in self._selected:
            self._selected.remove(attr)
        else:
            self._selected.append(attr)
        self._on_change(self._selected)
        self._render_trigger.set(self._render_trigger() + 1)


class RulesEditor(Component):
    """Editor for conditional rules (dynamic list)."""

    def __init__(
        self,
        rules: list[dict],
        on_change: Callable[[list[dict]], None],
    ):
        super().__init__()
        self._rules = rules
        self._on_change = on_change

        self._condition_state = InputState("")
        self._formula_state = InputState("")
        self._description_state = InputState("")
        self._render_trigger = State(0)

        self._condition_state.attach(self)
        self._formula_state.attach(self)
        self._description_state.attach(self)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        items = []
        for i, rule in enumerate(self._rules):
            condition = rule.get("condition") or t("scorecard.default_rule")
            formula = rule.get("formula", "")
            desc = rule.get("description") or ""
            items.append(
                Column(
                    Row(
                        Text(f"#{i+1}", font_size=12)
                        .text_color(theme.colors.fg)
                        .fixed_width(30),
                        Text(condition[:40], font_size=12)
                        .text_color(theme.colors.text_primary)
                        .flex(1),
                        Button("x")
                        .on_click(lambda _, idx=i: self._remove(idx))
                        .fixed_width(28)
                        .fixed_height(28),
                    ).fixed_height(28),
                    Row(
                        Text("→", font_size=12).text_color(theme.colors.fg).fixed_width(30),
                        Text(formula[:50], font_size=12)
                        .text_color(theme.colors.text_success)
                        .flex(1),
                    ).fixed_height(24),
                )
                .fixed_height(56)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(4))

        return Column(
            Text(t("scorecard.rules"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Column(*items, scrollable=True).fixed_height(140),
            # Add new rule form
            Column(
                Row(
                    Text(t("scorecard.condition"), font_size=11).text_color(theme.colors.fg).fixed_width(70),
                    Input(self._condition_state).fixed_height(28).flex(1),
                ).fixed_height(32),
                Row(
                    Text(t("scorecard.formula"), font_size=11).text_color(theme.colors.fg).fixed_width(70),
                    Input(self._formula_state).fixed_height(28).flex(1),
                ).fixed_height(32),
                Row(
                    Spacer(),
                    Button(t("common.add")).on_click(self._add).fixed_width(60).fixed_height(28),
                ).fixed_height(32),
            ).fixed_height(100),
        ).fixed_height(270)

    def _add(self, _):
        formula = self._formula_state.value().strip()
        if formula:
            condition = self._condition_state.value().strip() or None
            self._rules.append({
                "condition": condition,
                "formula": formula,
                "description": self._description_state.value().strip() or None,
            })
            self._condition_state.set("")
            self._formula_state.set("")
            self._description_state.set("")
            self._on_change(self._rules)
            self._render_trigger.set(self._render_trigger() + 1)

    def _remove(self, index: int):
        if 0 <= index < len(self._rules):
            self._rules.pop(index)
            self._on_change(self._rules)
            self._render_trigger.set(self._render_trigger() + 1)


class LabelFunctionField(Component):
    """Editor for label function code with validation."""

    def __init__(
        self,
        label: str,
        code_state: MultilineInputState,
        score_refs: list[str],
        entity_refs: list[str],
        on_validation_change: Callable[[bool, str], None],
    ):
        super().__init__()
        self._label = label
        self._code_state = code_state
        self._score_refs = score_refs
        self._entity_refs = entity_refs
        self._on_validation_change = on_validation_change

        self._validation_status = State("")
        self._validation_status.attach(self)

        self._is_valid = State(True)
        self._is_valid.attach(self)

    def view(self):
        theme = ThemeManager().current
        status = self._validation_status()
        is_valid = self._is_valid()

        hint_text = "if score >= 90:\n    return 'S'\nelif entity.lifecycle == 'prod':\n    return 'A'\nelse:\n    return 'B'"

        return Column(
            Text(f"{self._label} *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            MultilineInput(self._code_state, font_size=13).fixed_height(160),
            Row(
                Button(t("common.validate")).on_click(self._validate).fixed_width(80).fixed_height(28),
                Spacer().fixed_width(16),
                Text(status, font_size=12).text_color(theme.colors.text_success if is_valid else theme.colors.text_danger),
                Spacer(),
            ).fixed_height(32),
            Text(t("scorecard.label_function_hint"), font_size=11).text_color(theme.colors.fg).fixed_height(40),
        ).fixed_height(260)

    def _validate(self, _):
        code = self._code_state.value()
        try:
            LabelFunctionEvaluator(
                label_function=code,
                score_refs=self._score_refs,
                entity_refs=self._entity_refs,
            )
            self._is_valid.set(True)
            self._validation_status.set("Valid")
            self._on_validation_change(True, "")
        except FormulaError as e:
            self._is_valid.set(False)
            self._validation_status.set(f"Error: {e}")
            self._on_validation_change(False, str(e))

    def update_refs(self, score_refs: list[str], entity_refs: list[str]):
        """Update the refs for validation."""
        self._score_refs = score_refs
        self._entity_refs = entity_refs


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
    """Editor for a single RankDefinition with 3 modes.

    Mode 1 (Simple): formula + thresholds
    Mode 2 (Conditional): rules (condition + formula pairs) + thresholds
    Mode 3 (Label Function): label_function code returning labels directly
    """

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
                    dict(th) if isinstance(th, dict) else {"min": th.min, "label": th.label}
                    for th in self._form_data["thresholds"]
                ]
            # Convert rules to list of dicts if needed
            if "rules" in self._form_data and self._form_data["rules"]:
                self._form_data["rules"] = [
                    dict(r) if isinstance(r, dict) else {
                        "condition": r.condition,
                        "formula": r.formula,
                        "description": r.description,
                    }
                    for r in self._form_data["rules"]
                ]
        else:
            self._form_data = {
                "id": "",
                "name": "",
                "description": "",
                "target_kinds": [],
                "score_refs": [],
                "entity_refs": [],
                "formula": "",
                "rules": [],
                "label_function": "",
                "thresholds": [],
            }

        # Determine initial mode
        if self._form_data.get("label_function"):
            initial_mode = RANK_MODE_LABEL_FUNCTION
        elif self._form_data.get("rules"):
            initial_mode = RANK_MODE_CONDITIONAL
        else:
            initial_mode = RANK_MODE_SIMPLE

        # Mode state
        self._mode = State(initial_mode)
        self._mode.attach(self)

        # Form states
        self._id_state = InputState(self._form_data.get("id", ""))
        self._name_state = InputState(self._form_data.get("name", ""))
        self._description_state = MultilineInputState(
            self._form_data.get("description") or ""
        )
        self._formula_state = MultilineInputState(self._form_data.get("formula") or "")
        self._label_function_state = MultilineInputState(
            self._form_data.get("label_function") or ""
        )

        # Example code for label function hint (read-only display)
        self._example_code_state = MultilineInputState(
            "if security >= 90 and testing >= 80:\n"
            "    return 'S'\n"
            "elif entity.lifecycle == 'production':\n"
            "    return 'A'\n"
            "else:\n"
            "    return 'B'"
        )

        # Additional states for inline editors
        self._rule_condition_state = InputState("")
        self._rule_formula_state = InputState("")
        self._threshold_min_state = InputState("")
        self._threshold_label_state = InputState("")

        self._id_state.attach(self)
        self._name_state.attach(self)
        self._description_state.attach(self)
        self._formula_state.attach(self)
        self._label_function_state.attach(self)
        self._rule_condition_state.attach(self)
        self._rule_formula_state.attach(self)
        self._threshold_min_state.attach(self)
        self._threshold_label_state.attach(self)

        self._error = State("")
        self._error.attach(self)

        self._formula_valid = True
        self._label_function_valid = True
        self._formula_validation_status = ""
        self._label_function_validation_status = ""
        self._render_trigger = State(0)
        self._render_trigger.attach(self)

    def view(self):
        theme = ThemeManager().current
        error_text = self._error()
        mode = self._mode()
        score_refs = self._form_data.get("score_refs", [])
        entity_refs = self._form_data.get("entity_refs", [])

        # Build target kinds buttons inline
        target_kinds = self._form_data.get("target_kinds", [])
        kind_buttons = []
        for kind in ENTITY_KINDS:
            is_selected = kind in target_kinds
            kind_buttons.append(
                Button(kind)
                .on_click(lambda _, k=kind: self._toggle_target_kind(k))
                .fixed_height(28)
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
            )
            kind_buttons.append(Spacer().fixed_width(4))

        # Build score refs buttons inline
        score_buttons = []
        for score_id in self._available_scores:
            is_selected = score_id in score_refs
            score_buttons.append(
                Button(score_id)
                .on_click(lambda _, s=score_id: self._toggle_score_ref(s))
                .fixed_height(28)
                .bg_color(theme.colors.text_success if is_selected else theme.colors.bg_secondary)
            )
            score_buttons.append(Spacer().fixed_width(4))
        if not self._available_scores:
            score_buttons.append(Text(t("scorecard.no_scores_defined"), font_size=12).text_color(theme.colors.fg))

        # Build mode selector inline
        mode_buttons = Row(
            Button(t("scorecard.mode_simple"))
            .on_click(lambda _: self._set_mode(RANK_MODE_SIMPLE))
            .bg_color(theme.colors.bg_selected if mode == RANK_MODE_SIMPLE else theme.colors.bg_secondary)
            .fixed_height(28),
            Spacer().fixed_width(4),
            Button(t("scorecard.mode_conditional"))
            .on_click(lambda _: self._set_mode(RANK_MODE_CONDITIONAL))
            .bg_color(theme.colors.bg_selected if mode == RANK_MODE_CONDITIONAL else theme.colors.bg_secondary)
            .fixed_height(28),
            Spacer().fixed_width(4),
            Button(t("scorecard.mode_label_function"))
            .on_click(lambda _: self._set_mode(RANK_MODE_LABEL_FUNCTION))
            .bg_color(theme.colors.bg_selected if mode == RANK_MODE_LABEL_FUNCTION else theme.colors.bg_secondary)
            .fixed_height(28),
            Spacer(),
        ).fixed_height(32)

        # Build mode-specific content
        mode_content = self._build_mode_content(mode, score_refs, entity_refs, theme)

        return Column(
            # ID
            Text(t("scorecard.id") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            Input(self._id_state).fixed_height(32),
            Spacer().fixed_height(4),
            # Name
            Text(t("entity.field.name") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            Input(self._name_state).fixed_height(32),
            Spacer().fixed_height(4),
            # Description
            Text(t("entity.field.description"), font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            MultilineInput(self._description_state, font_size=13).fixed_height(36),
            Spacer().fixed_height(4),
            # Target Kinds
            Text(t("scorecard.target_kinds"), font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            Row(*kind_buttons).fixed_height(32),
            Spacer().fixed_height(4),
            # Score Refs
            Text(t("scorecard.score_refs") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            Row(*score_buttons).fixed_height(32),
            Spacer().fixed_height(4),
            # Mode selector
            Text(t("scorecard.mode"), font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
            mode_buttons,
            Spacer().fixed_height(4),
            # Mode-specific content
            mode_content,
            Spacer().fixed_height(8),
            # Error message
            Text(error_text, font_size=12).text_color(theme.colors.text_danger).fixed_height(20) if error_text else Spacer().fixed_height(4),
            # Buttons
            Row(
                Spacer(),
                Button(t("common.cancel")).on_click(lambda _: self._on_cancel()).fixed_width(80).fixed_height(32),
                Spacer().fixed_width(8),
                Button(t("common.save")).on_click(self._save).bg_color(theme.colors.text_success).fixed_width(80).fixed_height(32),
            ).fixed_height(36),
        )

    def _toggle_target_kind(self, kind: str):
        """Toggle target kind selection."""
        target_kinds = self._form_data.get("target_kinds", [])
        if kind in target_kinds:
            target_kinds.remove(kind)
        else:
            target_kinds.append(kind)
        self._form_data["target_kinds"] = target_kinds
        self._render_trigger.set(self._render_trigger() + 1)

    def _toggle_score_ref(self, score_id: str):
        """Toggle score ref selection."""
        score_refs = self._form_data.get("score_refs", [])
        if score_id in score_refs:
            score_refs.remove(score_id)
        else:
            score_refs.append(score_id)
        self._form_data["score_refs"] = score_refs
        self._render_trigger.set(self._render_trigger() + 1)

    def _build_mode_content(self, mode: str, score_refs: list[str], entity_refs: list[str], theme) -> Component:
        """Build content for the selected mode."""
        if mode == RANK_MODE_SIMPLE:
            # Mode 1: Simple formula + thresholds
            return Column(
                # Formula field (inline)
                Column(
                    Text(t("scorecard.formula") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
                    MultilineInput(self._formula_state, font_size=13).fixed_height(60),
                    Row(
                        Button(t("common.validate")).on_click(self._validate_formula).fixed_width(80).fixed_height(28),
                        Spacer().fixed_width(16),
                        Text(self._formula_validation_msg(), font_size=12).text_color(
                            theme.colors.text_success if self._formula_valid else theme.colors.text_danger
                        ),
                        Spacer(),
                    ).fixed_height(32),
                ).fixed_height(120),
                # Thresholds
                self._build_thresholds_section(theme),
            )

        elif mode == RANK_MODE_CONDITIONAL:
            # Mode 2: Conditional rules + entity refs + thresholds
            return Column(
                # Entity refs selector (inline)
                self._build_entity_refs_selector(entity_refs, theme),
                # Rules editor (inline)
                self._build_rules_section(theme),
                # Thresholds
                self._build_thresholds_section(theme),
            )

        else:
            # Mode 3: Label function + entity refs (no thresholds)
            return Column(
                # Entity refs selector (inline)
                self._build_entity_refs_selector(entity_refs, theme),
                # Label function field (inline)
                Text(t("scorecard.label_function") + " *", font_size=13).text_color(theme.colors.text_primary).fixed_height(18),
                MultilineInput(self._label_function_state, font_size=12).fixed_height(160),
                Row(
                    Button(t("common.validate")).on_click(self._validate_label_function).fixed_width(80).fixed_height(28),
                    Spacer().fixed_width(16),
                    Text(self._label_function_validation_msg(), font_size=12).text_color(
                        theme.colors.text_success if self._label_function_valid else theme.colors.text_danger
                    ),
                    Spacer(),
                ).fixed_height(32),
                Spacer().fixed_height(8),
                Text(t("scorecard.label_function_example"), font_size=11).text_color(theme.colors.fg).fixed_height(16),
                # Example code in read-only multiline input
                MultilineInput(self._example_code_state, font_size=10).fixed_height(100),
            )

    def _build_entity_refs_selector(self, entity_refs: list[str], theme) -> Component:
        """Build inline entity refs selector."""
        buttons = []
        for attr in ENTITY_ATTRS:
            is_selected = attr in entity_refs
            btn = (
                Button(attr)
                .on_click(lambda _, a=attr: self._toggle_entity_ref(a))
                .fixed_height(28)
                .bg_color(theme.colors.bg_selected if is_selected else theme.colors.bg_secondary)
            )
            buttons.append(btn)
            buttons.append(Spacer().fixed_width(4))

        return Column(
            Text(t("scorecard.entity_refs"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Row(*buttons).fixed_height(32),
        ).fixed_height(56)

    def _build_rules_section(self, theme) -> Component:
        """Build inline rules editor."""
        rules = self._form_data.get("rules") or []
        items = []
        for i, rule in enumerate(rules):
            condition = rule.get("condition") or t("scorecard.default_rule")
            formula = rule.get("formula", "")
            items.append(
                Row(
                    Text(f"#{i+1}", font_size=12).text_color(theme.colors.fg).fixed_width(24),
                    Column(
                        Text(condition[:35] + "..." if len(condition) > 35 else condition, font_size=11)
                        .text_color(theme.colors.text_primary),
                        Text("→ " + (formula[:40] + "..." if len(formula) > 40 else formula), font_size=11)
                        .text_color(theme.colors.text_success),
                    ).flex(1),
                    Button("x")
                    .on_click(lambda _, idx=i: self._remove_rule(idx))
                    .fixed_width(24)
                    .fixed_height(24),
                )
                .fixed_height(40)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(2))

        # Calculate height based on items
        rules_list_height = min(len(items) * 42, 120) if items else 0
        total_height = 20 + rules_list_height + 32 + 32 + 8  # title + list + condition row + formula row + spacing

        components = [
            Text(t("scorecard.rules"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
        ]
        if items:
            components.append(Column(*items).fixed_height(rules_list_height))
        components.extend([
            # Add new rule form
            Row(
                Text(t("scorecard.condition"), font_size=11).text_color(theme.colors.fg).fixed_width(50),
                Input(self._rule_condition_state).fixed_height(28).flex(1),
            ).fixed_height(32),
            Row(
                Text(t("scorecard.formula"), font_size=11).text_color(theme.colors.fg).fixed_width(50),
                Input(self._rule_formula_state).fixed_height(28).flex(1),
                Spacer().fixed_width(8),
                Button(t("common.add")).on_click(self._add_rule).fixed_width(50).fixed_height(28),
            ).fixed_height(32),
        ])
        return Column(*components).fixed_height(total_height)

    def _build_thresholds_section(self, theme) -> Component:
        """Build inline thresholds editor."""
        thresholds = self._form_data.get("thresholds", [])
        items = []
        for i, th in enumerate(thresholds):
            items.append(
                Row(
                    Text(f"{th['min']}", font_size=12).text_color(theme.colors.text_primary).fixed_width(50),
                    Text("→", font_size=12).text_color(theme.colors.fg).fixed_width(24),
                    Text(th["label"], font_size=12).text_color(theme.colors.text_success).fixed_width(60),
                    Spacer(),
                    Button("x")
                    .on_click(lambda _, idx=i: self._remove_threshold(idx))
                    .fixed_width(24)
                    .fixed_height(24),
                )
                .fixed_height(28)
                .bg_color(theme.colors.bg_secondary)
            )
            items.append(Spacer().fixed_height(2))

        return Column(
            Text(t("scorecard.thresholds"), font_size=13).text_color(theme.colors.text_primary).fixed_height(20),
            Column(*items, scrollable=True).fixed_height(100) if items else Spacer().fixed_height(100),
            Row(
                Input(self._threshold_min_state).fixed_width(60).fixed_height(28),
                Spacer().fixed_width(8),
                Text("→", font_size=12).text_color(theme.colors.fg).fixed_width(24),
                Spacer().fixed_width(8),
                Input(self._threshold_label_state).fixed_width(60).fixed_height(28),
                Spacer().fixed_width(8),
                Button(t("common.add")).on_click(self._add_threshold).fixed_width(50).fixed_height(28),
                Spacer(),
            ).fixed_height(32),
        ).fixed_height(160)

    def _toggle_entity_ref(self, attr: str):
        """Toggle entity ref selection."""
        entity_refs = self._form_data.get("entity_refs", [])
        if attr in entity_refs:
            entity_refs.remove(attr)
        else:
            entity_refs.append(attr)
        self._form_data["entity_refs"] = entity_refs
        self._render_trigger.set(self._render_trigger() + 1)

    def _add_rule(self, _):
        """Add a new rule."""
        formula = self._rule_formula_state.value().strip()
        if formula:
            rules = self._form_data.get("rules") or []
            condition = self._rule_condition_state.value().strip() or None
            rules.append({
                "condition": condition,
                "formula": formula,
                "description": None,
            })
            self._form_data["rules"] = rules
            self._rule_condition_state.set("")
            self._rule_formula_state.set("")
            self._render_trigger.set(self._render_trigger() + 1)

    def _remove_rule(self, index: int):
        """Remove a rule by index."""
        rules = self._form_data.get("rules") or []
        if 0 <= index < len(rules):
            rules.pop(index)
            self._form_data["rules"] = rules
            self._render_trigger.set(self._render_trigger() + 1)

    def _add_threshold(self, _):
        """Add a new threshold."""
        try:
            min_val = float(self._threshold_min_state.value())
            label = self._threshold_label_state.value().strip()
            if label:
                thresholds = self._form_data.get("thresholds", [])
                thresholds.append({"min": min_val, "label": label})
                thresholds.sort(key=lambda t: t["min"], reverse=True)
                self._form_data["thresholds"] = thresholds
                self._threshold_min_state.set("")
                self._threshold_label_state.set("")
                self._render_trigger.set(self._render_trigger() + 1)
        except ValueError:
            pass

    def _remove_threshold(self, index: int):
        """Remove a threshold by index."""
        thresholds = self._form_data.get("thresholds", [])
        if 0 <= index < len(thresholds):
            thresholds.pop(index)
            self._form_data["thresholds"] = thresholds
            self._render_trigger.set(self._render_trigger() + 1)

    def _validate_formula(self, _):
        """Validate the formula."""
        formula = self._formula_state.value()
        score_refs = self._form_data.get("score_refs", [])
        try:
            SafeFormulaEvaluator(formula, score_refs)
            self._formula_valid = True
            self._formula_validation_status = "Valid"
        except FormulaError as e:
            self._formula_valid = False
            self._formula_validation_status = f"Error: {e}"
        self._render_trigger.set(self._render_trigger() + 1)

    def _formula_validation_msg(self) -> str:
        """Get formula validation message."""
        return getattr(self, "_formula_validation_status", "")

    def _validate_label_function(self, _):
        """Validate the label function."""
        code = self._label_function_state.value()
        score_refs = self._form_data.get("score_refs", [])
        entity_refs = self._form_data.get("entity_refs", [])
        try:
            LabelFunctionEvaluator(
                label_function=code,
                score_refs=score_refs,
                entity_refs=entity_refs,
            )
            self._label_function_valid = True
            self._label_function_validation_status = "Valid"
        except FormulaError as e:
            self._label_function_valid = False
            self._label_function_validation_status = f"Error: {e}"
        self._render_trigger.set(self._render_trigger() + 1)

    def _label_function_validation_msg(self) -> str:
        """Get label function validation message."""
        return getattr(self, "_label_function_validation_status", "")

    def _set_mode(self, mode: str):
        """Set the current mode."""
        self._mode.set(mode)
        self._error.set("")
        self._render_trigger.set(self._render_trigger() + 1)

    def _on_score_refs_change(self, refs: list[str]):
        self._form_data["score_refs"] = refs
        self._render_trigger.set(self._render_trigger() + 1)

    def _on_entity_refs_change(self, refs: list[str]):
        self._form_data["entity_refs"] = refs
        self._render_trigger.set(self._render_trigger() + 1)

    def _on_formula_validation(self, is_valid: bool, error: str):
        self._formula_valid = is_valid

    def _on_label_function_validation(self, is_valid: bool, error: str):
        self._label_function_valid = is_valid

    def _save(self, _):
        # Validate common fields
        id_val = self._id_state.value().strip()
        name_val = self._name_state.value().strip()
        mode = self._mode()
        score_refs = self._form_data.get("score_refs", [])
        entity_refs = self._form_data.get("entity_refs", [])

        if not id_val:
            self._error.set(t("validation.required", field=t("scorecard.id")))
            return
        if not name_val:
            self._error.set(t("validation.required", field=t("entity.field.name")))
            return

        result = {
            "id": id_val,
            "name": name_val,
            "description": self._description_state.value().strip() or None,
            "target_kinds": self._form_data.get("target_kinds", []),
            "score_refs": score_refs,
            "entity_refs": entity_refs,
            "formula": None,
            "rules": None,
            "label_function": None,
            "thresholds": [],
        }

        if mode == RANK_MODE_SIMPLE:
            # Validate simple mode
            formula = self._formula_state.value().strip()
            if not score_refs:
                self._error.set(t("validation.required", field=t("scorecard.score_refs")))
                return
            if not formula:
                self._error.set(t("validation.required", field=t("scorecard.formula")))
                return

            try:
                SafeFormulaEvaluator(formula, score_refs)
            except FormulaError as e:
                self._error.set(t("validation.error", message=str(e)))
                return

            result["formula"] = formula
            result["thresholds"] = self._form_data.get("thresholds", [])

        elif mode == RANK_MODE_CONDITIONAL:
            # Validate conditional mode
            rules = self._form_data.get("rules") or []
            if not rules:
                self._error.set(t("validation.required", field=t("scorecard.rules")))
                return

            # Validate rules by building a RankDefinition and ConditionalRankEvaluator
            try:
                rank_def = RankDefinition(
                    id=id_val,
                    name=name_val,
                    score_refs=score_refs,
                    entity_refs=entity_refs,
                    rules=[
                        RankRule(
                            condition=r.get("condition"),
                            formula=r["formula"],
                            description=r.get("description"),
                        )
                        for r in rules
                    ],
                    thresholds=[
                        RankThreshold(min=th["min"], label=th["label"])
                        for th in self._form_data.get("thresholds", [])
                    ],
                )
                ConditionalRankEvaluator(rank_def)
            except (FormulaError, Exception) as e:
                self._error.set(t("validation.error", message=str(e)))
                return

            result["rules"] = rules
            result["thresholds"] = self._form_data.get("thresholds", [])

        else:
            # Validate label function mode
            label_function = self._label_function_state.value().strip()
            if not label_function:
                self._error.set(t("validation.required", field=t("scorecard.label_function")))
                return

            try:
                LabelFunctionEvaluator(
                    label_function=label_function,
                    score_refs=score_refs,
                    entity_refs=entity_refs,
                )
            except FormulaError as e:
                self._error.set(t("validation.error", message=str(e)))
                return

            result["label_function"] = label_function
            # No thresholds for label function mode

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
        # Rank editor needs more height for conditional mode
        modal_height = 700 if self._editing_type == "score" else 1000
        modal = Modal(
            content=modal_content,
            state=self._modal_state,
            title=(
                t("scorecard.edit_score")
                if self._editing_type == "score"
                else t("scorecard.edit_rank")
            ),
            width=600,
            height=modal_height,
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
            ranks = []
            for r in self._rank_definitions:
                # Build rules if present
                rules = None
                if r.get("rules"):
                    rules = [
                        RankRule(
                            condition=rule.get("condition"),
                            formula=rule["formula"],
                            description=rule.get("description"),
                        )
                        for rule in r["rules"]
                    ]

                # Build thresholds
                thresholds = [
                    RankThreshold(min=th["min"], label=th["label"])
                    for th in r.get("thresholds", [])
                ]

                ranks.append(
                    RankDefinition(
                        id=r["id"],
                        name=r["name"],
                        description=r.get("description"),
                        target_kinds=r.get("target_kinds", []),
                        score_refs=r.get("score_refs", []),
                        entity_refs=r.get("entity_refs", []),
                        formula=r.get("formula"),
                        rules=rules,
                        label_function=r.get("label_function"),
                        thresholds=thresholds,
                    )
                )

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
