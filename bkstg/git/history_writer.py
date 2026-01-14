"""Write history YAML files."""

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


def normalize_entity_id(entity_id: str) -> str:
    """Normalize entity_id to be safe for filenames.

    Example: "Component:default/user-service" -> "Component_default_user-service"
    """
    return entity_id.replace(":", "_").replace("/", "_")


class HistoryWriter:
    """Write history data to YAML files."""

    def __init__(self, base_path: Path):
        """Initialize with base catalog path."""
        self.base_path = base_path
        self.history_path = base_path / "history"
        self.scores_path = self.history_path / "scores"
        self.ranks_path = self.history_path / "ranks"
        self.definitions_path = self.history_path / "definitions"

    def _ensure_dirs(self) -> None:
        """Ensure history directories exist."""
        self.scores_path.mkdir(parents=True, exist_ok=True)
        self.ranks_path.mkdir(parents=True, exist_ok=True)
        self.definitions_path.mkdir(parents=True, exist_ok=True)

    def _get_score_history_path(self, entity_id: str) -> Path:
        """Get path for entity score history file."""
        filename = f"{normalize_entity_id(entity_id)}.yaml"
        return self.scores_path / filename

    def _get_rank_history_path(self, entity_id: str) -> Path:
        """Get path for entity rank history file."""
        filename = f"{normalize_entity_id(entity_id)}.yaml"
        return self.ranks_path / filename

    def _load_score_history(self, entity_id: str) -> EntityScoreHistory:
        """Load existing score history or create new one."""
        path = self._get_score_history_path(entity_id)
        if path.exists():
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
        return EntityScoreHistory(entity_id=entity_id)

    def _load_rank_history(self, entity_id: str) -> EntityRankHistory:
        """Load existing rank history or create new one."""
        path = self._get_rank_history_path(entity_id)
        if path.exists():
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
        return EntityRankHistory(entity_id=entity_id)

    def add_score_history_entry(
        self,
        entity_id: str,
        score_id: str,
        value: float,
        reason: str | None = None,
        source: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Add a score history entry and save to YAML."""
        self._ensure_dirs()

        history = self._load_score_history(entity_id)

        if score_id not in history.scores:
            history.scores[score_id] = ScoreHistory(score_id=score_id)

        from datetime import datetime

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"

        entry = ScoreHistoryEntry(
            timestamp=timestamp,
            value=value,
            reason=reason,
            source=source,
        )

        history.scores[score_id].entries.append(entry)

        self._save_score_history(history)

    def add_rank_history_entry(
        self,
        entity_id: str,
        rank_id: str,
        value: float,
        label: str | None = None,
        score_snapshot: dict[str, float] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Add a rank history entry and save to YAML."""
        self._ensure_dirs()

        history = self._load_rank_history(entity_id)

        if rank_id not in history.ranks:
            history.ranks[rank_id] = RankHistory(rank_id=rank_id)

        from datetime import datetime

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"

        entry = RankHistoryEntry(
            timestamp=timestamp,
            value=value,
            label=label,
            score_snapshot=score_snapshot or {},
        )

        history.ranks[rank_id].entries.append(entry)

        self._save_rank_history(history)

    def _save_score_history(self, history: EntityScoreHistory) -> None:
        """Save score history to YAML file."""
        path = self._get_score_history_path(history.entity_id)
        data = {
            "entity_id": history.entity_id,
            "scores": {
                score_id: {
                    "entries": [e.model_dump(exclude_none=True) for e in sh.entries]
                }
                for score_id, sh in history.scores.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def _save_rank_history(self, history: EntityRankHistory) -> None:
        """Save rank history to YAML file."""
        path = self._get_rank_history_path(history.entity_id)
        data = {
            "entity_id": history.entity_id,
            "ranks": {
                rank_id: {
                    "entries": [e.model_dump(exclude_none=True) for e in rh.entries]
                }
                for rank_id, rh in history.ranks.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    # ========== Definition History ==========

    def _load_score_definition_histories(self) -> AllScoreDefinitionHistories:
        """Load score definition histories."""
        path = self.definitions_path / "score_definitions.yaml"
        if path.exists():
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
        return AllScoreDefinitionHistories()

    def _load_rank_definition_histories(self) -> AllRankDefinitionHistories:
        """Load rank definition histories."""
        path = self.definitions_path / "rank_definitions.yaml"
        if path.exists():
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
        return AllRankDefinitionHistories()

    def add_score_definition_history_entry(
        self,
        score_id: str,
        change_type: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Add a score definition change history entry."""
        self._ensure_dirs()

        histories = self._load_score_definition_histories()

        if score_id not in histories.scores:
            histories.scores[score_id] = ScoreDefinitionHistory(score_id=score_id)

        from datetime import datetime

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"

        entry = DefinitionChangeEntry(
            timestamp=timestamp,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            changed_fields=changed_fields or [],
        )

        histories.scores[score_id].entries.append(entry)

        self._save_score_definition_histories(histories)

    def add_rank_definition_history_entry(
        self,
        rank_id: str,
        change_type: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Add a rank definition change history entry."""
        self._ensure_dirs()

        histories = self._load_rank_definition_histories()

        if rank_id not in histories.ranks:
            histories.ranks[rank_id] = RankDefinitionHistory(rank_id=rank_id)

        from datetime import datetime

        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"

        entry = DefinitionChangeEntry(
            timestamp=timestamp,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            changed_fields=changed_fields or [],
        )

        histories.ranks[rank_id].entries.append(entry)

        self._save_rank_definition_histories(histories)

    def _save_score_definition_histories(
        self, histories: AllScoreDefinitionHistories
    ) -> None:
        """Save score definition histories to YAML."""
        path = self.definitions_path / "score_definitions.yaml"
        data = {
            "scores": {
                score_id: {
                    "entries": [e.model_dump(exclude_none=True) for e in sdh.entries]
                }
                for score_id, sdh in histories.scores.items()
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def _save_rank_definition_histories(
        self, histories: AllRankDefinitionHistories
    ) -> None:
        """Save rank definition histories to YAML."""
        path = self.definitions_path / "rank_definitions.yaml"
        data = {
            "ranks": {
                rank_id: {
                    "entries": [e.model_dump(exclude_none=True) for e in rdh.entries]
                }
                for rank_id, rdh in histories.ranks.items()
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    # ========== Definition Change Snapshots ==========

    def _get_snapshots_path(self) -> Path:
        """Get path for definition change snapshots directory."""
        return self.definitions_path / "snapshots"

    def _load_snapshots(self, definition_id: str) -> list[dict[str, Any]]:
        """Load existing snapshots for a definition."""
        path = self._get_snapshots_path() / f"{definition_id}.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("snapshots", [])
        return []

    def add_definition_change_snapshot(
        self,
        definition_id: str,
        timestamp: str,
        total_affected: int,
        impacts: list[dict[str, Any]],
        scorecard_id: str | None = None,
    ) -> None:
        """Add a definition change snapshot to YAML.

        Args:
            definition_id: The rank definition ID
            timestamp: ISO timestamp for the snapshot
            total_affected: Number of entities affected (excluding unchanged)
            impacts: List of dicts with entity_id, before_value/label, after_value/label, change_type
            scorecard_id: Optional scorecard ID
        """
        self._ensure_dirs()
        snapshots_path = self._get_snapshots_path()
        snapshots_path.mkdir(parents=True, exist_ok=True)

        # Load existing snapshots
        snapshots = self._load_snapshots(definition_id)

        # Create new snapshot entry
        snapshot_entry = {
            "timestamp": timestamp,
            "total_affected": total_affected,
            "impacts": [
                {
                    "entity_id": i["entity_id"],
                    "before_value": i.get("before_value"),
                    "before_label": i.get("before_label"),
                    "after_value": i.get("after_value"),
                    "after_label": i.get("after_label"),
                    "change_type": i["change_type"],
                }
                for i in impacts
                if i["change_type"] != "unchanged"  # Only save affected entities
            ],
        }

        if scorecard_id:
            snapshot_entry["scorecard_id"] = scorecard_id

        snapshots.append(snapshot_entry)

        # Save to YAML
        path = snapshots_path / f"{definition_id}.yaml"
        data = {
            "definition_id": definition_id,
            "snapshots": snapshots,
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
