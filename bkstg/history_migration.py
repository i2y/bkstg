"""Migration utility for converting old history YAML format to composite key format.

Old format uses plain score_id/rank_id as dict keys:
  scores:
    documentation:
      entries: [...]

New format uses 'scorecard_id:score_id' composite keys:
  scores:
    tech-health:documentation:
      entries: [...]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .git.history_writer import _make_history_key, _parse_history_key

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of a history migration run."""

    migrated: int = 0
    skipped: int = 0
    unresolved: int = 0
    errors: int = 0
    details: list[str] = field(default_factory=list)


def _build_score_id_to_scorecard_mapping(
    score_defs: dict[str, str],
) -> dict[str, list[str]]:
    """Build mapping from score_id to list of scorecard_ids.

    Args:
        score_defs: Dict mapping score_id -> scorecard_id (from DB).

    Returns:
        Dict mapping score_id -> list of scorecard_ids that define it.
    """
    mapping: dict[str, list[str]] = {}
    for score_id, scorecard_id in score_defs.items():
        if score_id not in mapping:
            mapping[score_id] = []
        mapping[score_id].append(scorecard_id)
    return mapping


def _build_rank_id_to_scorecard_mapping(
    rank_defs: dict[str, str],
) -> dict[str, list[str]]:
    """Build mapping from rank_id to list of scorecard_ids."""
    mapping: dict[str, list[str]] = {}
    for rank_id, scorecard_id in rank_defs.items():
        if rank_id not in mapping:
            mapping[rank_id] = []
        mapping[rank_id].append(scorecard_id)
    return mapping


def _resolve_scorecard_id(
    item_id: str,
    entity_id: str,
    id_to_scorecards: dict[str, list[str]],
    entity_scores: dict[str, str] | None = None,
) -> str | None:
    """Try to resolve the scorecard_id for an item_id.

    Args:
        item_id: The score_id or rank_id.
        entity_id: The entity ID (for entity_scores lookup).
        id_to_scorecards: Mapping from item_id to list of scorecard_ids.
        entity_scores: Optional mapping from (entity_id, item_id) -> scorecard_id.

    Returns:
        The resolved scorecard_id, or None if unresolvable.
    """
    scorecards = id_to_scorecards.get(item_id, [])

    if len(scorecards) == 1:
        return scorecards[0]

    if len(scorecards) == 0:
        return None

    # Multiple scorecards - try entity_scores for disambiguation
    if entity_scores:
        key = f"{entity_id}:{item_id}"
        scorecard_id = entity_scores.get(key)
        if scorecard_id:
            return scorecard_id

    # Cannot resolve
    return None


def migrate_score_history_file(
    file_path: Path,
    score_id_to_scorecards: dict[str, list[str]],
    entity_scores: dict[str, str] | None = None,
) -> MigrationResult:
    """Migrate a single score history YAML file.

    Args:
        file_path: Path to the score history YAML file.
        score_id_to_scorecards: Mapping from score_id to list of scorecard_ids.
        entity_scores: Optional mapping from "entity_id:score_id" -> scorecard_id.

    Returns:
        MigrationResult with counts.
    """
    result = MigrationResult()

    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        result.errors += 1
        result.details.append(f"Error reading {file_path}: {e}")
        return result

    entity_id = data.get("entity_id", file_path.stem)
    scores = data.get("scores", {})

    if not scores:
        return result

    new_scores: dict[str, dict] = {}
    needs_migration = False

    for key, score_data in scores.items():
        _item_id, existing_scorecard_id = _parse_history_key(key)

        if existing_scorecard_id is not None:
            # Already in new format
            new_scores[key] = score_data
            result.skipped += 1
            continue

        # Old format - try to resolve scorecard_id
        score_id = key
        scorecard_id = _resolve_scorecard_id(
            score_id, entity_id, score_id_to_scorecards, entity_scores
        )

        if scorecard_id:
            new_key = _make_history_key(score_id, scorecard_id)
            new_scores[new_key] = score_data
            result.migrated += 1
            needs_migration = True
            result.details.append(
                f"  {file_path.name}: {score_id} -> {new_key}"
            )
        else:
            # Cannot resolve - keep old format
            new_scores[key] = score_data
            result.unresolved += 1
            result.details.append(
                f"  {file_path.name}: {score_id} - unresolved"
            )

    if needs_migration:
        data["scores"] = new_scores
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    return result


def migrate_rank_history_file(
    file_path: Path,
    rank_id_to_scorecards: dict[str, list[str]],
    entity_scores: dict[str, str] | None = None,
) -> MigrationResult:
    """Migrate a single rank history YAML file.

    Args:
        file_path: Path to the rank history YAML file.
        rank_id_to_scorecards: Mapping from rank_id to list of scorecard_ids.
        entity_scores: Optional mapping from "entity_id:rank_id" -> scorecard_id.

    Returns:
        MigrationResult with counts.
    """
    result = MigrationResult()

    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        result.errors += 1
        result.details.append(f"Error reading {file_path}: {e}")
        return result

    entity_id = data.get("entity_id", file_path.stem)
    ranks = data.get("ranks", {})

    if not ranks:
        return result

    new_ranks: dict[str, dict] = {}
    needs_migration = False

    for key, rank_data in ranks.items():
        _item_id, existing_scorecard_id = _parse_history_key(key)

        if existing_scorecard_id is not None:
            # Already in new format
            new_ranks[key] = rank_data
            result.skipped += 1
            continue

        # Old format - try to resolve scorecard_id
        rank_id = key
        scorecard_id = _resolve_scorecard_id(
            rank_id, entity_id, rank_id_to_scorecards, entity_scores
        )

        if scorecard_id:
            new_key = _make_history_key(rank_id, scorecard_id)
            new_ranks[new_key] = rank_data
            result.migrated += 1
            needs_migration = True
            result.details.append(
                f"  {file_path.name}: {rank_id} -> {new_key}"
            )
        else:
            # Cannot resolve - keep old format
            new_ranks[key] = rank_data
            result.unresolved += 1
            result.details.append(
                f"  {file_path.name}: {rank_id} - unresolved"
            )

    if needs_migration:
        data["ranks"] = new_ranks
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    return result


def migrate_history_files(
    catalog_path: Path,
    score_defs: dict[str, str],
    rank_defs: dict[str, str],
    entity_scores: dict[str, str] | None = None,
) -> MigrationResult:
    """Migrate all history YAML files in a catalog directory.

    Args:
        catalog_path: Path to the catalogs directory containing history/.
        score_defs: Dict mapping score_id -> scorecard_id (from score_definitions table).
        rank_defs: Dict mapping rank_id -> scorecard_id (from rank_definitions table).
        entity_scores: Optional dict mapping "entity_id:score_id" -> scorecard_id
                      (from entity_scores table, for disambiguation).

    Returns:
        MigrationResult with total counts.
    """
    total_result = MigrationResult()

    scores_path = catalog_path / "history" / "scores"
    ranks_path = catalog_path / "history" / "ranks"

    score_id_to_scorecards = _build_score_id_to_scorecard_mapping(score_defs)
    rank_id_to_scorecards = _build_rank_id_to_scorecard_mapping(rank_defs)

    # Migrate score history files
    if scores_path.exists():
        for yaml_file in scores_path.glob("*.yaml"):
            file_result = migrate_score_history_file(
                yaml_file, score_id_to_scorecards, entity_scores
            )
            total_result.migrated += file_result.migrated
            total_result.skipped += file_result.skipped
            total_result.unresolved += file_result.unresolved
            total_result.errors += file_result.errors
            total_result.details.extend(file_result.details)

    # Migrate rank history files
    if ranks_path.exists():
        for yaml_file in ranks_path.glob("*.yaml"):
            file_result = migrate_rank_history_file(
                yaml_file, rank_id_to_scorecards, entity_scores
            )
            total_result.migrated += file_result.migrated
            total_result.skipped += file_result.skipped
            total_result.unresolved += file_result.unresolved
            total_result.errors += file_result.errors
            total_result.details.extend(file_result.details)

    logger.info(
        f"Migration complete: {total_result.migrated} migrated, "
        f"{total_result.skipped} skipped, "
        f"{total_result.unresolved} unresolved, "
        f"{total_result.errors} errors"
    )

    return total_result
