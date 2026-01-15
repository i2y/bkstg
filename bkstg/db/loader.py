"""Load catalog entities into DuckDB."""

import json
from pathlib import Path

import duckdb

from ..git.history_reader import HistoryReader
from ..models import Catalog, Entity
from ..models.base import EntityKind
from ..models.scorecard import ScorecardDefinition, RankDefinition
from ..scorecard.evaluator import (
    ConditionalRankEvaluator,
    EntityContext,
    FormulaError,
    LabelFunctionEvaluator,
    SafeFormulaEvaluator,
)


# Mapping from lowercase kind to proper case
KIND_MAPPING = {
    "component": "Component",
    "api": "API",
    "resource": "Resource",
    "system": "System",
    "domain": "Domain",
    "user": "User",
    "group": "Group",
    "location": "Location",
}


def normalize_entity_ref(ref: str) -> str:
    """Normalize entity reference to proper case.

    Converts 'resource:default/redis-cache' to 'Resource:default/redis-cache'
    """
    if ":" in ref:
        kind_part, rest = ref.split(":", 1)
        normalized_kind = KIND_MAPPING.get(kind_part.lower(), kind_part)
        return f"{normalized_kind}:{rest}"
    return ref


class CatalogLoader:
    """Load catalog entities into DuckDB."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
        self._rank_evaluators: dict[str, SafeFormulaEvaluator | ConditionalRankEvaluator] = {}
        self._rank_definitions: dict[str, RankDefinition] = {}

    def load_catalog(
        self,
        catalog: Catalog,
        file_paths: dict[str, Path] | None = None,
    ) -> None:
        """Load all entities from catalog into database."""
        # Clear existing data
        self.conn.execute("DELETE FROM relations")
        self.conn.execute("DELETE FROM entities")
        # Reset sequence by dropping and recreating
        self.conn.execute("DROP SEQUENCE IF EXISTS relations_id_seq")
        self.conn.execute("CREATE SEQUENCE relations_id_seq START 1")

        # Insert entities
        file_paths = file_paths or {}
        for entity in catalog.all_entities():
            file_path = file_paths.get(entity.entity_id)
            self._insert_entity(entity, file_path)

        # Build relations
        self._build_relations(catalog)

        # Load scores from entities
        self._load_entity_scores(catalog)

    def _insert_entity(self, entity: Entity, file_path: Path | None = None) -> None:
        """Insert a single entity."""
        # Extract common fields
        owner = None
        lifecycle = None
        entity_type = None
        system = None
        domain = None

        if hasattr(entity, "spec"):
            spec = entity.spec
            owner = getattr(spec, "owner", None)
            lifecycle = getattr(spec, "lifecycle", None)
            entity_type = getattr(spec, "type", None)
            system = getattr(spec, "system", None)
            domain = getattr(spec, "domain", None)

        self.conn.execute(
            """
            INSERT INTO entities (
                id, kind, namespace, name, title, description,
                owner, lifecycle, type, system, domain,
                tags, labels, file_path, raw_yaml
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entity.entity_id,
                entity.kind.value,
                entity.metadata.namespace,
                entity.metadata.name,
                entity.metadata.title,
                entity.metadata.description,
                owner,
                lifecycle,
                entity_type,
                system,
                domain,
                entity.metadata.tags,
                json.dumps(entity.metadata.labels),
                str(file_path) if file_path else None,
                json.dumps(entity.model_dump(exclude_none=True)),
            ],
        )

    def _build_relations(self, catalog: Catalog) -> None:
        """Extract and insert relations from entities."""
        relations = []

        for entity in catalog.all_entities():
            source_id = entity.entity_id

            # Owner relation
            if hasattr(entity.spec, "owner") and entity.spec.owner:
                relations.append((source_id, entity.spec.owner, "ownedBy"))

            # System relation
            if hasattr(entity.spec, "system") and entity.spec.system:
                relations.append((source_id, entity.spec.system, "partOf"))

            # Domain relation
            if hasattr(entity.spec, "domain") and entity.spec.domain:
                relations.append((source_id, entity.spec.domain, "partOfDomain"))

            # Dependencies
            if hasattr(entity.spec, "dependsOn"):
                for dep in entity.spec.dependsOn:
                    relations.append((source_id, dep, "dependsOn"))

            # Provides APIs
            if hasattr(entity.spec, "providesApis"):
                for api in entity.spec.providesApis:
                    relations.append((source_id, api, "providesApi"))

            # Consumes APIs
            if hasattr(entity.spec, "consumesApis"):
                for api in entity.spec.consumesApis:
                    relations.append((source_id, api, "consumesApi"))

            # Group membership (User)
            if hasattr(entity.spec, "memberOf"):
                for group in entity.spec.memberOf:
                    relations.append((source_id, group, "memberOf"))

            # Group hierarchy
            if hasattr(entity.spec, "parent") and entity.spec.parent:
                relations.append((source_id, entity.spec.parent, "childOf"))

            if hasattr(entity.spec, "children"):
                for child in entity.spec.children:
                    relations.append((source_id, child, "parentOf"))

            if hasattr(entity.spec, "members"):
                for member in entity.spec.members:
                    relations.append((source_id, member, "hasMember"))

            # Subdomain
            if hasattr(entity.spec, "subdomainOf") and entity.spec.subdomainOf:
                relations.append((source_id, entity.spec.subdomainOf, "subdomainOf"))

            # Subcomponent
            if hasattr(entity.spec, "subcomponentOf") and entity.spec.subcomponentOf:
                relations.append(
                    (source_id, entity.spec.subcomponentOf, "subcomponentOf")
                )

        # Insert all relations (normalize target IDs)
        for source_id, target_id, rel_type in relations:
            normalized_target = normalize_entity_ref(target_id)
            self.conn.execute(
                """
                INSERT INTO relations (id, source_id, target_id, relation_type)
                VALUES (nextval('relations_id_seq'), ?, ?, ?)
                """,
                [source_id, normalized_target, rel_type],
            )

    def _get_score_to_scorecard_mapping(self) -> dict[str, str]:
        """Get mapping from score_id to scorecard_id."""
        result = self.conn.execute(
            "SELECT id, scorecard_id FROM score_definitions WHERE scorecard_id IS NOT NULL"
        ).fetchall()
        return {row[0]: row[1] for row in result}

    def _get_rank_to_scorecard_mapping(self) -> dict[str, str]:
        """Get mapping from rank_id to scorecard_id."""
        result = self.conn.execute(
            "SELECT id, scorecard_id FROM rank_definitions WHERE scorecard_id IS NOT NULL"
        ).fetchall()
        return {row[0]: row[1] for row in result}

    def _load_entity_scores(self, catalog: Catalog) -> None:
        """Load scores from entity metadata into database."""
        # Clear existing scores
        self.conn.execute("DELETE FROM entity_scores")
        self.conn.execute("DELETE FROM entity_ranks")
        self.conn.execute("DROP SEQUENCE IF EXISTS entity_scores_id_seq")
        self.conn.execute("DROP SEQUENCE IF EXISTS entity_ranks_id_seq")
        self.conn.execute("CREATE SEQUENCE entity_scores_id_seq START 1")
        self.conn.execute("CREATE SEQUENCE entity_ranks_id_seq START 1")

        # Build score_id -> scorecard_id mapping
        score_to_scorecard = self._get_score_to_scorecard_mapping()

        for entity in catalog.all_entities():
            entity_id = entity.entity_id
            scores = entity.metadata.scores

            # Group scores by scorecard_id for rank computation
            scores_by_scorecard: dict[str, dict[str, float]] = {}

            for score in scores:
                # Get scorecard_id from score definition, or use explicit one if provided
                scorecard_id = score.scorecard_id or score_to_scorecard.get(score.score_id)
                self.conn.execute(
                    """
                    INSERT INTO entity_scores (id, entity_id, score_id, value, reason, updated_at, scorecard_id)
                    VALUES (nextval('entity_scores_id_seq'), ?, ?, ?, ?, ?, ?)
                    """,
                    [entity_id, score.score_id, score.value, score.reason, score.updated_at, scorecard_id],
                )

                # Group scores by scorecard_id
                if scorecard_id:
                    if scorecard_id not in scores_by_scorecard:
                        scores_by_scorecard[scorecard_id] = {}
                    scores_by_scorecard[scorecard_id][score.score_id] = score.value

            # Compute ranks for this entity per scorecard
            for scorecard_id, scorecard_scores in scores_by_scorecard.items():
                self._compute_entity_ranks(entity_id, scorecard_scores, scorecard_id)

    def _compute_entity_ranks(
        self, entity_id: str, scores: dict[str, float], scorecard_id: str
    ) -> None:
        """Compute and store ranks for an entity based on its scores.

        Args:
            entity_id: The entity ID
            scores: Dictionary of score_id -> value for this scorecard
            scorecard_id: The scorecard ID to compute ranks for
        """
        # Get entity data for context
        result = self.conn.execute(
            """
            SELECT kind, type, lifecycle, owner, system, domain,
                   namespace, name, title, description, tags
            FROM entities WHERE id = ?
            """,
            [entity_id],
        ).fetchone()
        if not result:
            return

        # Build entity context
        entity_context = EntityContext(
            kind=result[0],
            type=result[1],
            lifecycle=result[2],
            owner=result[3],
            system=result[4],
            domain=result[5],
            namespace=result[6] or "default",
            name=result[7],
            title=result[8],
            description=result[9],
            tags=result[10] or [],
        )
        entity_kind = entity_context.kind

        # Get rank definitions for this specific scorecard only
        rank_defs = self.conn.execute("""
            SELECT id, score_refs, formula, target_kinds, rules, label_function, entity_refs, scorecard_id
            FROM rank_definitions
            WHERE scorecard_id = ?
        """, [scorecard_id]).fetchall()

        for rank_id, score_refs, formula, target_kinds, rules_json, label_function, entity_refs, _ in rank_defs:
            # Check if this rank applies to this entity kind
            if target_kinds and entity_kind not in target_kinds:
                continue

            # Use composite key to support same rank_id across different scorecards
            cache_key = f"{scorecard_id}:{rank_id}"

            # Get or create evaluator
            if cache_key not in self._rank_evaluators:
                rank_def = self._rank_definitions.get(cache_key)
                if not rank_def:
                    continue

                try:
                    if rank_def.has_label_function():
                        # Mode 3: Label function (returns label directly)
                        self._rank_evaluators[cache_key] = LabelFunctionEvaluator(
                            label_function=rank_def.label_function or "",
                            score_refs=rank_def.score_refs,
                            entity_refs=rank_def.entity_refs,
                        )
                    elif rank_def.has_conditional_rules():
                        # Mode 2: Conditional rules
                        self._rank_evaluators[cache_key] = ConditionalRankEvaluator(rank_def)
                    else:
                        # Mode 1: Simple formula (backwards compatible)
                        self._rank_evaluators[cache_key] = SafeFormulaEvaluator(
                            formula or "", score_refs or []
                        )
                except FormulaError:
                    continue

            evaluator = self._rank_evaluators[cache_key]

            # Check if we have all required scores (not needed for label function without score refs)
            required_refs = set(score_refs or [])
            if required_refs and not required_refs.issubset(set(scores.keys())):
                continue

            try:
                # Evaluate based on evaluator type
                if isinstance(evaluator, LabelFunctionEvaluator):
                    # Label function returns the label directly
                    label = evaluator.evaluate(scores, entity_context)
                    if label is None:
                        continue
                    # For label function mode, value is not meaningful, use 0
                    rank_value = 0.0
                elif isinstance(evaluator, ConditionalRankEvaluator):
                    rank_value = evaluator.evaluate(scores, entity_context)
                    if rank_value is None:
                        continue
                    # Get label from thresholds
                    label = None
                    if cache_key in self._rank_definitions:
                        label = self._rank_definitions[cache_key].get_label(rank_value)
                else:
                    rank_value = evaluator.evaluate(scores)
                    # Get label from thresholds
                    label = None
                    if cache_key in self._rank_definitions:
                        label = self._rank_definitions[cache_key].get_label(rank_value)

                self.conn.execute(
                    """
                    INSERT INTO entity_ranks (id, entity_id, rank_id, value, label, scorecard_id)
                    VALUES (nextval('entity_ranks_id_seq'), ?, ?, ?, ?, ?)
                    """,
                    [entity_id, rank_id, rank_value, label, scorecard_id],
                )
            except FormulaError:
                continue

    def load_scorecard_definitions(
        self, scorecard: ScorecardDefinition, scorecard_id: str | None = None
    ) -> None:
        """Load score and rank definitions from a ScorecardDefinition.

        Args:
            scorecard: The scorecard definition to load
            scorecard_id: Scorecard ID. If None, uses scorecard.metadata.name.
        """
        # Use metadata.name as scorecard_id if not provided
        if scorecard_id is None:
            scorecard_id = scorecard.metadata.name

        # Clear existing definitions for this scorecard
        self.conn.execute(
            "DELETE FROM rank_definitions WHERE scorecard_id = ?", [scorecard_id]
        )
        self.conn.execute(
            "DELETE FROM score_definitions WHERE scorecard_id = ?", [scorecard_id]
        )
        # Clear evaluators for this scorecard
        keys_to_remove = [
            k for k in self._rank_evaluators if k.startswith(f"{scorecard_id}:")
        ]
        for k in keys_to_remove:
            del self._rank_evaluators[k]
            if k in self._rank_definitions:
                del self._rank_definitions[k]

        # Register/update scorecard in scorecards table
        self._register_scorecard(scorecard, scorecard_id)

        # Insert score definitions
        for score_def in scorecard.spec.scores:
            # Convert levels to JSON if present
            levels_json = None
            if score_def.levels:
                levels_json = json.dumps([
                    {"label": lvl.label, "value": lvl.value, "description": lvl.description}
                    for lvl in score_def.levels
                ])
            self.conn.execute(
                """
                INSERT INTO score_definitions (id, name, description, target_kinds, min_value, max_value, scorecard_id, levels)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    score_def.id,
                    score_def.name,
                    score_def.description,
                    score_def.target_kinds,
                    score_def.min_value,
                    score_def.max_value,
                    scorecard_id,
                    levels_json,
                ],
            )

        # Insert rank definitions and pre-compile evaluators
        for rank_def in scorecard.spec.ranks:
            # Convert thresholds to JSON
            thresholds_json = json.dumps([
                {"min": t.min, "label": t.label}
                for t in rank_def.thresholds
            ]) if rank_def.thresholds else None

            # Convert rules to JSON
            rules_json = None
            if rank_def.rules:
                rules_json = json.dumps([
                    {
                        "condition": r.condition,
                        "formula": r.formula,
                        "description": r.description,
                    }
                    for r in rank_def.rules
                ])

            self.conn.execute(
                """
                INSERT INTO rank_definitions (
                    id, name, description, target_kinds, score_refs,
                    formula, rules, label_function, entity_refs, thresholds, scorecard_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    rank_def.id,
                    rank_def.name,
                    rank_def.description,
                    rank_def.target_kinds,
                    rank_def.score_refs,
                    rank_def.formula,
                    rules_json,
                    rank_def.label_function,
                    rank_def.entity_refs,
                    thresholds_json,
                    scorecard_id,
                ],
            )

            # Store rank definition for label computation
            # Use composite key to support same rank_id across different scorecards
            cache_key = f"{scorecard_id}:{rank_def.id}"
            self._rank_definitions[cache_key] = rank_def

            # Pre-compile evaluator
            try:
                if rank_def.has_label_function():
                    # Mode 3: Label function (returns label directly)
                    self._rank_evaluators[cache_key] = LabelFunctionEvaluator(
                        label_function=rank_def.label_function or "",
                        score_refs=rank_def.score_refs,
                        entity_refs=rank_def.entity_refs,
                    )
                elif rank_def.has_conditional_rules():
                    # Mode 2: Conditional rules
                    self._rank_evaluators[cache_key] = ConditionalRankEvaluator(rank_def)
                elif rank_def.formula:
                    # Mode 1: Simple formula
                    self._rank_evaluators[cache_key] = SafeFormulaEvaluator(
                        rank_def.formula, rank_def.score_refs
                    )
            except FormulaError as e:
                print(f"Warning: Invalid formula for rank {rank_def.id}: {e}")

    def _register_scorecard(
        self, scorecard: ScorecardDefinition, scorecard_id: str
    ) -> None:
        """Register or update a scorecard in the scorecards table.

        Args:
            scorecard: The scorecard definition
            scorecard_id: The scorecard ID
        """
        from datetime import datetime

        # Check if scorecard exists
        existing = self.conn.execute(
            "SELECT id FROM scorecards WHERE id = ?", [scorecard_id]
        ).fetchone()

        status = scorecard.status.value if hasattr(scorecard, "status") else "active"
        now = datetime.utcnow().isoformat() + "Z"

        if existing:
            # Update existing scorecard
            self.conn.execute(
                """
                UPDATE scorecards
                SET name = ?, description = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                [
                    scorecard.metadata.name,
                    scorecard.metadata.description,
                    status,
                    now,
                    scorecard_id,
                ],
            )
        else:
            # Insert new scorecard
            self.conn.execute(
                """
                INSERT INTO scorecards (id, name, description, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    scorecard_id,
                    scorecard.metadata.name,
                    scorecard.metadata.description,
                    status,
                    now,
                    now,
                ],
            )

    def clear_history(self) -> None:
        """Clear all history data from database."""
        self.conn.execute("DELETE FROM score_history")
        self.conn.execute("DELETE FROM rank_history")
        self.conn.execute("DELETE FROM definition_history")
        self.conn.execute("DROP SEQUENCE IF EXISTS score_history_id_seq")
        self.conn.execute("DROP SEQUENCE IF EXISTS rank_history_id_seq")
        self.conn.execute("DROP SEQUENCE IF EXISTS definition_history_id_seq")
        self.conn.execute("CREATE SEQUENCE score_history_id_seq START 1")
        self.conn.execute("CREATE SEQUENCE rank_history_id_seq START 1")
        self.conn.execute("CREATE SEQUENCE definition_history_id_seq START 1")

    def load_history(self, catalog_path: Path, clear: bool = True) -> None:
        """Load history data from YAML files into database.

        Args:
            catalog_path: Path to the directory containing history/ subdirectory.
            clear: Whether to clear existing history before loading. Default True.
        """
        if clear:
            self.clear_history()

        reader = HistoryReader(catalog_path)

        # Load score history entries
        for entry in reader.get_all_score_history_entries():
            self.conn.execute(
                """
                INSERT INTO score_history (id, entity_id, score_id, value, reason, source, recorded_at)
                VALUES (nextval('score_history_id_seq'), ?, ?, ?, ?, ?, ?)
                """,
                [
                    entry["entity_id"],
                    entry["score_id"],
                    entry["value"],
                    entry.get("reason"),
                    entry.get("source"),
                    entry["recorded_at"],
                ],
            )

        # Load rank history entries
        for entry in reader.get_all_rank_history_entries():
            score_snapshot_json = (
                json.dumps(entry["score_snapshot"]) if entry.get("score_snapshot") else None
            )
            self.conn.execute(
                """
                INSERT INTO rank_history (id, entity_id, rank_id, value, label, score_snapshot, recorded_at)
                VALUES (nextval('rank_history_id_seq'), ?, ?, ?, ?, ?, ?)
                """,
                [
                    entry["entity_id"],
                    entry["rank_id"],
                    entry["value"],
                    entry.get("label"),
                    score_snapshot_json,
                    entry["recorded_at"],
                ],
            )

        # Load definition history entries
        for entry in reader.get_all_definition_history_entries():
            old_value_json = json.dumps(entry["old_value"]) if entry.get("old_value") else None
            new_value_json = json.dumps(entry["new_value"]) if entry.get("new_value") else None
            changed_fields_json = (
                json.dumps(entry["changed_fields"]) if entry.get("changed_fields") else None
            )
            self.conn.execute(
                """
                INSERT INTO definition_history
                (id, definition_type, definition_id, change_type, old_value, new_value, changed_fields, recorded_at)
                VALUES (nextval('definition_history_id_seq'), ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    entry["definition_type"],
                    entry["definition_id"],
                    entry["change_type"],
                    old_value_json,
                    new_value_json,
                    changed_fields_json,
                    entry["recorded_at"],
                ],
            )
