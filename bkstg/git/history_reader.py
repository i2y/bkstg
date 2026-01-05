"""Read history YAML files."""

from pathlib import Path
from typing import Any

import yaml

from ..models.history import (
    AllRankDefinitionHistories,
    AllScoreDefinitionHistories,
    DefinitionChangeEntry,
    EntityRankHistory,
    EntityScoreHistory,
    RankDefinitionHistory,
    RankHistory,
    RankHistoryEntry,
    ScoreDefinitionHistory,
    ScoreHistory,
    ScoreHistoryEntry,
)
from .history_writer import normalize_entity_id


class HistoryReader:
    """Read history data from YAML files."""

    def __init__(self, base_path: Path):
        """Initialize with base catalog path."""
        self.base_path = base_path
        self.history_path = base_path / "history"
        self.scores_path = self.history_path / "scores"
        self.ranks_path = self.history_path / "ranks"
        self.definitions_path = self.history_path / "definitions"

    def _get_score_history_path(self, entity_id: str) -> Path:
        """Get path for entity score history file."""
        filename = f"{normalize_entity_id(entity_id)}.yaml"
        return self.scores_path / filename

    def _get_rank_history_path(self, entity_id: str) -> Path:
        """Get path for entity rank history file."""
        filename = f"{normalize_entity_id(entity_id)}.yaml"
        return self.ranks_path / filename

    # ========== Score History ==========

    def read_entity_score_history(self, entity_id: str) -> EntityScoreHistory | None:
        """Read score history for a specific entity."""
        path = self._get_score_history_path(entity_id)
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return EntityScoreHistory(
            entity_id=data.get("entity_id", entity_id),
            scores={
                score_id: ScoreHistory(
                    score_id=score_id,
                    entries=[
                        ScoreHistoryEntry(**e) for e in score_data.get("entries", [])
                    ],
                )
                for score_id, score_data in data.get("scores", {}).items()
            },
        )

    def read_all_score_histories(self) -> list[EntityScoreHistory]:
        """Read all entity score histories."""
        if not self.scores_path.exists():
            return []

        histories = []
        for yaml_path in self.scores_path.glob("*.yaml"):
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            entity_id = data.get("entity_id", yaml_path.stem)
            history = EntityScoreHistory(
                entity_id=entity_id,
                scores={
                    score_id: ScoreHistory(
                        score_id=score_id,
                        entries=[
                            ScoreHistoryEntry(**e)
                            for e in score_data.get("entries", [])
                        ],
                    )
                    for score_id, score_data in data.get("scores", {}).items()
                },
            )
            histories.append(history)

        return histories

    # ========== Rank History ==========

    def read_entity_rank_history(self, entity_id: str) -> EntityRankHistory | None:
        """Read rank history for a specific entity."""
        path = self._get_rank_history_path(entity_id)
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return EntityRankHistory(
            entity_id=data.get("entity_id", entity_id),
            ranks={
                rank_id: RankHistory(
                    rank_id=rank_id,
                    entries=[
                        RankHistoryEntry(**e) for e in rank_data.get("entries", [])
                    ],
                )
                for rank_id, rank_data in data.get("ranks", {}).items()
            },
        )

    def read_all_rank_histories(self) -> list[EntityRankHistory]:
        """Read all entity rank histories."""
        if not self.ranks_path.exists():
            return []

        histories = []
        for yaml_path in self.ranks_path.glob("*.yaml"):
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            entity_id = data.get("entity_id", yaml_path.stem)
            history = EntityRankHistory(
                entity_id=entity_id,
                ranks={
                    rank_id: RankHistory(
                        rank_id=rank_id,
                        entries=[
                            RankHistoryEntry(**e) for e in rank_data.get("entries", [])
                        ],
                    )
                    for rank_id, rank_data in data.get("ranks", {}).items()
                },
            )
            histories.append(history)

        return histories

    # ========== Definition History ==========

    def read_score_definition_histories(self) -> AllScoreDefinitionHistories:
        """Read score definition change histories."""
        path = self.definitions_path / "score_definitions.yaml"
        if not path.exists():
            return AllScoreDefinitionHistories()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return AllScoreDefinitionHistories(
            scores={
                score_id: ScoreDefinitionHistory(
                    score_id=score_id,
                    entries=[
                        DefinitionChangeEntry(**e)
                        for e in score_data.get("entries", [])
                    ],
                )
                for score_id, score_data in data.get("scores", {}).items()
            }
        )

    def read_rank_definition_histories(self) -> AllRankDefinitionHistories:
        """Read rank definition change histories."""
        path = self.definitions_path / "rank_definitions.yaml"
        if not path.exists():
            return AllRankDefinitionHistories()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return AllRankDefinitionHistories(
            ranks={
                rank_id: RankDefinitionHistory(
                    rank_id=rank_id,
                    entries=[
                        DefinitionChangeEntry(**e)
                        for e in rank_data.get("entries", [])
                    ],
                )
                for rank_id, rank_data in data.get("ranks", {}).items()
            }
        )

    # ========== Flattened Data for DB Loading ==========

    def get_all_score_history_entries(self) -> list[dict[str, Any]]:
        """Get all score history entries flattened for DB loading."""
        entries = []
        for history in self.read_all_score_histories():
            for score_id, score_history in history.scores.items():
                for entry in score_history.entries:
                    entries.append(
                        {
                            "entity_id": history.entity_id,
                            "score_id": score_id,
                            "value": entry.value,
                            "reason": entry.reason,
                            "source": entry.source,
                            "recorded_at": entry.timestamp,
                        }
                    )
        return entries

    def get_all_rank_history_entries(self) -> list[dict[str, Any]]:
        """Get all rank history entries flattened for DB loading."""
        entries = []
        for history in self.read_all_rank_histories():
            for rank_id, rank_history in history.ranks.items():
                for entry in rank_history.entries:
                    entries.append(
                        {
                            "entity_id": history.entity_id,
                            "rank_id": rank_id,
                            "value": entry.value,
                            "label": entry.label,
                            "score_snapshot": entry.score_snapshot,
                            "recorded_at": entry.timestamp,
                        }
                    )
        return entries

    def get_all_definition_history_entries(self) -> list[dict[str, Any]]:
        """Get all definition change history entries flattened for DB loading."""
        entries = []

        score_histories = self.read_score_definition_histories()
        for score_id, sdh in score_histories.scores.items():
            for entry in sdh.entries:
                entries.append(
                    {
                        "definition_type": "score",
                        "definition_id": score_id,
                        "change_type": entry.change_type,
                        "old_value": entry.old_value,
                        "new_value": entry.new_value,
                        "changed_fields": entry.changed_fields,
                        "recorded_at": entry.timestamp,
                    }
                )

        rank_histories = self.read_rank_definition_histories()
        for rank_id, rdh in rank_histories.ranks.items():
            for entry in rdh.entries:
                entries.append(
                    {
                        "definition_type": "rank",
                        "definition_id": rank_id,
                        "change_type": entry.change_type,
                        "old_value": entry.old_value,
                        "new_value": entry.new_value,
                        "changed_fields": entry.changed_fields,
                        "recorded_at": entry.timestamp,
                    }
                )

        return entries
