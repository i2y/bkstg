"""Safe formula evaluator using AST parsing."""

from __future__ import annotations

import ast
import logging
import math
import operator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..models.scorecard import RankDefinition

logger = logging.getLogger(__name__)


# Allowed entity attributes for entity.* access
ALLOWED_ENTITY_ATTRS = frozenset({
    "kind", "type", "lifecycle", "owner", "system", "domain",
    "namespace", "name", "title", "description", "tags",
})

# Allowed binary operators
SAFE_BINARY_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Allowed comparison operators
SAFE_COMPARE_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

# Allowed unary operators
SAFE_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_avg(*args: float) -> float:
    """Calculate average of values."""
    if not args:
        return 0.0
    return sum(args) / len(args)


# Allowed functions
SAFE_FUNCTIONS: dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "sum": sum,
    "avg": _safe_avg,
    "round": round,
    "pow": pow,
}

# Extended functions for enhanced evaluator
SAFE_FUNCTIONS_EXTENDED: dict[str, Any] = {
    **SAFE_FUNCTIONS,
    "len": len,
    "str": str,
    "bool": bool,
    "any": any,
    "all": all,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
}


class EntityContext(BaseModel):
    """Entity context for formula evaluation with entity.* access."""

    kind: str = Field(..., description="Entity kind (Component, API, etc.)")
    type: str | None = Field(default=None, description="Entity type (service, library, etc.)")
    lifecycle: str | None = Field(default=None, description="Lifecycle stage (production, experimental, etc.)")
    owner: str | None = Field(default=None, description="Owner reference")
    system: str | None = Field(default=None, description="System reference")
    domain: str | None = Field(default=None, description="Domain reference")
    namespace: str = Field(default="default", description="Entity namespace")
    name: str = Field(..., description="Entity name")
    title: str | None = Field(default=None, description="Entity title")
    description: str | None = Field(default=None, description="Entity description")
    tags: list[str] = Field(default_factory=list, description="Entity tags")

    class Config:
        frozen = True


class FormulaError(Exception):
    """Error in formula parsing or evaluation."""

    pass


class SafeFormulaEvaluator:
    """Safely evaluate rank formulas without using eval().

    Only allows:
    - Arithmetic operators: +, -, *, /, //, %, **
    - Comparison operators: ==, !=, <, <=, >, >=
    - Unary operators: +, -
    - Functions: min, max, abs, sum, avg, round, pow
    - Ternary expressions: x if condition else y
    - Variables from score_refs

    Example:
        evaluator = SafeFormulaEvaluator(
            formula="security * 0.4 + documentation * 0.3 + testing * 0.3",
            score_refs=["security", "documentation", "testing"]
        )
        result = evaluator.evaluate({
            "security": 85,
            "documentation": 70,
            "testing": 90
        })
    """

    MAX_DEPTH = 50  # Maximum AST nesting depth

    def __init__(self, formula: str, score_refs: list[str]):
        """Initialize with formula and allowed variable names.

        Args:
            formula: Python expression string
            score_refs: List of allowed variable names (score IDs)

        Raises:
            FormulaError: If formula is invalid or uses disallowed operations
        """
        self.formula = formula
        self.score_refs = set(score_refs)
        self._ast = self._parse_and_validate(formula)

    def _parse_and_validate(self, formula: str) -> ast.Expression:
        """Parse formula and validate it only uses allowed operations."""
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            raise FormulaError(f"Invalid formula syntax: {e}") from e

        self._validate_node(tree.body, depth=0)
        return tree

    def _validate_node(self, node: ast.AST, depth: int) -> None:
        """Recursively validate AST nodes."""
        if depth > self.MAX_DEPTH:
            raise FormulaError("Formula is too complex (max depth exceeded)")

        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise FormulaError(f"Only numeric constants allowed, got: {type(node.value).__name__}")

        elif isinstance(node, ast.Name):
            if node.id not in self.score_refs and node.id not in SAFE_FUNCTIONS:
                raise FormulaError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.BinOp):
            if type(node.op) not in SAFE_BINARY_OPS:
                raise FormulaError(f"Operator not allowed: {type(node.op).__name__}")
            self._validate_node(node.left, depth + 1)
            self._validate_node(node.right, depth + 1)

        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in SAFE_UNARY_OPS:
                raise FormulaError(f"Unary operator not allowed: {type(node.op).__name__}")
            self._validate_node(node.operand, depth + 1)

        elif isinstance(node, ast.Compare):
            if not all(type(op) in SAFE_COMPARE_OPS for op in node.ops):
                raise FormulaError("Comparison operator not allowed")
            self._validate_node(node.left, depth + 1)
            for comparator in node.comparators:
                self._validate_node(comparator, depth + 1)

        elif isinstance(node, ast.IfExp):
            # Ternary expression: x if condition else y
            self._validate_node(node.test, depth + 1)
            self._validate_node(node.body, depth + 1)
            self._validate_node(node.orelse, depth + 1)

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FormulaError("Only simple function calls allowed")
            if node.func.id not in SAFE_FUNCTIONS:
                raise FormulaError(f"Function not allowed: {node.func.id}")
            if node.keywords:
                raise FormulaError("Keyword arguments not allowed in function calls")
            for arg in node.args:
                self._validate_node(arg, depth + 1)

        elif isinstance(node, ast.Tuple | ast.List):
            # Allow tuples/lists for function arguments like min(a, b, c)
            for elt in node.elts:
                self._validate_node(elt, depth + 1)

        else:
            raise FormulaError(f"Expression type not allowed: {type(node).__name__}")

    def evaluate(self, scores: dict[str, float]) -> float:
        """Evaluate the formula with the given score values.

        Args:
            scores: Dictionary mapping score IDs to their values

        Returns:
            Computed rank value

        Raises:
            FormulaError: If required scores are missing or evaluation fails
        """
        # Verify all required scores are provided
        missing = self.score_refs - set(scores.keys())
        if missing:
            raise FormulaError(f"Missing required scores: {', '.join(sorted(missing))}")

        # Build context with scores and safe functions
        context = {**scores, **SAFE_FUNCTIONS}

        try:
            return float(self._eval_node(self._ast.body, context))
        except Exception as e:
            raise FormulaError(f"Evaluation failed: {e}") from e

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> float:
        """Recursively evaluate AST nodes."""
        if isinstance(node, ast.Constant):
            return float(node.value)

        elif isinstance(node, ast.Name):
            value = context[node.id]
            if callable(value):
                return value  # Return function for Call handling
            return float(value)

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = SAFE_BINARY_OPS[type(node.op)]
            return float(op_func(left, right))

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op_func = SAFE_UNARY_OPS[type(node.op)]
            return float(op_func(operand))

        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = SAFE_COMPARE_OPS[type(op)]
                if not op_func(left, right):
                    return 0.0  # False as float
                left = right
            return 1.0  # True as float

        elif isinstance(node, ast.IfExp):
            test_result = self._eval_node(node.test, context)
            if test_result:
                return self._eval_node(node.body, context)
            else:
                return self._eval_node(node.orelse, context)

        elif isinstance(node, ast.Call):
            func = context[node.func.id]
            args = [self._eval_node(arg, context) for arg in node.args]
            return float(func(*args))

        elif isinstance(node, ast.Tuple | ast.List):
            return [self._eval_node(elt, context) for elt in node.elts]

        raise FormulaError(f"Cannot evaluate node: {type(node).__name__}")


class EnhancedFormulaEvaluator:
    """Enhanced formula evaluator with entity.* attribute support.

    Extends SafeFormulaEvaluator functionality with:
    - Access to entity attributes via entity.kind, entity.type, etc.
    - 'in' and 'not in' operators for tag membership checking
    - Additional safe functions (len, str, bool, any, all, sqrt, floor, ceil)
    - String constant support for comparisons

    Example:
        evaluator = EnhancedFormulaEvaluator(
            formula="security * 0.5 + testing * 0.3 if entity.lifecycle == 'production' else security * 0.3 + testing * 0.5",
            score_refs=["security", "testing"],
            entity_refs=["lifecycle"]
        )
        result = evaluator.evaluate(
            scores={"security": 85, "testing": 90},
            entity_context=EntityContext(kind="Component", name="my-service", lifecycle="production")
        )
    """

    MAX_DEPTH = 50
    MAX_FORMULA_LENGTH = 10000

    def __init__(
        self,
        formula: str,
        score_refs: list[str] | None = None,
        entity_refs: list[str] | None = None,
    ):
        """Initialize with formula and allowed references.

        Args:
            formula: Python expression string
            score_refs: List of allowed score variable names
            entity_refs: List of entity attributes that may be referenced

        Raises:
            FormulaError: If formula is invalid or uses disallowed operations
        """
        if len(formula) > self.MAX_FORMULA_LENGTH:
            raise FormulaError(f"Formula too long (max {self.MAX_FORMULA_LENGTH} chars)")

        self.formula = formula
        self.score_refs = set(score_refs or [])
        self.entity_refs = set(entity_refs or [])
        self._functions = SAFE_FUNCTIONS_EXTENDED
        self._ast = self._parse_and_validate(formula)

    def _parse_and_validate(self, formula: str) -> ast.Expression:
        """Parse formula and validate it only uses allowed operations."""
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            raise FormulaError(f"Invalid formula syntax: {e}") from e

        self._validate_node(tree.body, depth=0)
        return tree

    def _validate_node(self, node: ast.AST, depth: int) -> None:
        """Recursively validate AST nodes with entity.* support."""
        if depth > self.MAX_DEPTH:
            raise FormulaError("Formula is too complex (max depth exceeded)")

        if isinstance(node, ast.Constant):
            # Allow numeric and string constants
            if not isinstance(node.value, (int, float, str)):
                raise FormulaError(f"Only numeric and string constants allowed, got: {type(node.value).__name__}")

        elif isinstance(node, ast.Name):
            # Allow score refs, function names, and 'entity'
            if node.id not in self.score_refs and node.id not in self._functions and node.id != "entity":
                raise FormulaError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.Attribute):
            # Only allow entity.attr access
            if isinstance(node.value, ast.Name) and node.value.id == "entity":
                if node.attr not in ALLOWED_ENTITY_ATTRS:
                    raise FormulaError(f"Entity attribute not allowed: entity.{node.attr}")
            else:
                raise FormulaError("Only entity.attribute access is allowed")

        elif isinstance(node, ast.BinOp):
            if type(node.op) not in SAFE_BINARY_OPS:
                raise FormulaError(f"Operator not allowed: {type(node.op).__name__}")
            self._validate_node(node.left, depth + 1)
            self._validate_node(node.right, depth + 1)

        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in SAFE_UNARY_OPS:
                raise FormulaError(f"Unary operator not allowed: {type(node.op).__name__}")
            self._validate_node(node.operand, depth + 1)

        elif isinstance(node, ast.BoolOp):
            # Allow 'and' and 'or'
            for value in node.values:
                self._validate_node(value, depth + 1)

        elif isinstance(node, ast.Compare):
            # Allow comparison operators including 'in' and 'not in'
            for op in node.ops:
                if type(op) not in SAFE_COMPARE_OPS and not isinstance(op, (ast.In, ast.NotIn)):
                    raise FormulaError(f"Comparison operator not allowed: {type(op).__name__}")
            self._validate_node(node.left, depth + 1)
            for comparator in node.comparators:
                self._validate_node(comparator, depth + 1)

        elif isinstance(node, ast.IfExp):
            self._validate_node(node.test, depth + 1)
            self._validate_node(node.body, depth + 1)
            self._validate_node(node.orelse, depth + 1)

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FormulaError("Only simple function calls allowed")
            if node.func.id not in self._functions:
                raise FormulaError(f"Function not allowed: {node.func.id}")
            if node.keywords:
                raise FormulaError("Keyword arguments not allowed in function calls")
            for arg in node.args:
                self._validate_node(arg, depth + 1)

        elif isinstance(node, ast.Tuple | ast.List):
            for elt in node.elts:
                self._validate_node(elt, depth + 1)

        else:
            raise FormulaError(f"Expression type not allowed: {type(node).__name__}")

    def evaluate(
        self,
        scores: dict[str, float] | None = None,
        entity_context: EntityContext | None = None,
    ) -> float:
        """Evaluate the formula with scores and entity context.

        Args:
            scores: Dictionary mapping score IDs to their values
            entity_context: Entity context for entity.* access

        Returns:
            Computed value as float

        Raises:
            FormulaError: If evaluation fails
        """
        scores = scores or {}

        # Check required scores
        if self.score_refs:
            missing = self.score_refs - set(scores.keys())
            if missing:
                raise FormulaError(f"Missing required scores: {', '.join(sorted(missing))}")

        # Build context
        context: dict[str, Any] = {**scores, **self._functions}
        if entity_context:
            context["entity"] = entity_context

        try:
            result = self._eval_node(self._ast.body, context)
            # Handle boolean results
            if isinstance(result, bool):
                return 1.0 if result else 0.0
            return float(result)
        except Exception as e:
            raise FormulaError(f"Evaluation failed: {e}") from e

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        """Recursively evaluate AST nodes."""
        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            value = context.get(node.id)
            if callable(value):
                return value
            return value

        elif isinstance(node, ast.Attribute):
            # Handle entity.attr
            if isinstance(node.value, ast.Name) and node.value.id == "entity":
                entity = context.get("entity")
                if entity is None:
                    return None
                return getattr(entity, node.attr, None)
            raise FormulaError("Only entity.attribute access is allowed")

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = SAFE_BINARY_OPS[type(node.op)]
            return op_func(left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op_func = SAFE_UNARY_OPS[type(node.op)]
            return op_func(operand)

        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._eval_node(value, context):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_node(value, context):
                        return True
                return False

        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                if isinstance(op, ast.In):
                    if left not in (right or []):
                        return False
                elif isinstance(op, ast.NotIn):
                    if left in (right or []):
                        return False
                else:
                    op_func = SAFE_COMPARE_OPS[type(op)]
                    if not op_func(left, right):
                        return False
                left = right
            return True

        elif isinstance(node, ast.IfExp):
            test_result = self._eval_node(node.test, context)
            if test_result:
                return self._eval_node(node.body, context)
            else:
                return self._eval_node(node.orelse, context)

        elif isinstance(node, ast.Call):
            func = context[node.func.id]
            args = [self._eval_node(arg, context) for arg in node.args]
            return func(*args)

        elif isinstance(node, ast.Tuple | ast.List):
            return [self._eval_node(elt, context) for elt in node.elts]

        raise FormulaError(f"Cannot evaluate node: {type(node).__name__}")


class ConditionalRankEvaluator:
    """Evaluator for conditional rank definitions with multiple rules.

    Evaluates rules in order and returns the result of the first matching rule.
    If no rule matches, returns None.

    Example:
        evaluator = ConditionalRankEvaluator(rank_def)
        result = evaluator.evaluate(
            scores={"security": 85, "testing": 90},
            entity_context=EntityContext(kind="Component", name="my-service", lifecycle="production")
        )
    """

    MAX_RULES = 50

    def __init__(self, rank_def: RankDefinition):
        """Initialize with a rank definition.

        Args:
            rank_def: RankDefinition with formula and/or rules

        Raises:
            FormulaError: If any formula is invalid
        """
        self.rank_def = rank_def
        self._rule_evaluators: list[tuple[EnhancedFormulaEvaluator | None, EnhancedFormulaEvaluator]] = []
        self._compile_rules()

    def _compile_rules(self) -> None:
        """Pre-compile all conditions and formulas."""
        # Simple formula mode (backwards compatible)
        if self.rank_def.formula and not self.rank_def.rules:
            try:
                formula_eval = EnhancedFormulaEvaluator(
                    formula=self.rank_def.formula,
                    score_refs=self.rank_def.score_refs,
                    entity_refs=self.rank_def.entity_refs,
                )
                self._rule_evaluators.append((None, formula_eval))
            except FormulaError as e:
                logger.warning(f"Failed to compile formula for rank {self.rank_def.id}: {e}")
                raise

        # Conditional rules mode
        elif self.rank_def.rules:
            if len(self.rank_def.rules) > self.MAX_RULES:
                raise FormulaError(f"Too many rules (max {self.MAX_RULES})")

            for rule in self.rank_def.rules:
                condition_eval = None
                if rule.condition and rule.condition.strip() not in ("", "True", "true"):
                    try:
                        condition_eval = EnhancedFormulaEvaluator(
                            formula=rule.condition,
                            score_refs=[],  # Conditions don't use scores
                            entity_refs=self.rank_def.entity_refs,
                        )
                    except FormulaError as e:
                        logger.warning(f"Failed to compile condition for rank {self.rank_def.id}: {e}")
                        raise

                try:
                    formula_eval = EnhancedFormulaEvaluator(
                        formula=rule.formula,
                        score_refs=self.rank_def.score_refs,
                        entity_refs=self.rank_def.entity_refs,
                    )
                except FormulaError as e:
                    logger.warning(f"Failed to compile rule formula for rank {self.rank_def.id}: {e}")
                    raise

                self._rule_evaluators.append((condition_eval, formula_eval))

    def evaluate(
        self,
        scores: dict[str, float],
        entity_context: EntityContext,
    ) -> float | None:
        """Evaluate the first matching rule.

        Args:
            scores: Dictionary mapping score IDs to their values
            entity_context: Entity context for conditions

        Returns:
            Computed rank value, or None if no rule matches
        """
        for condition_eval, formula_eval in self._rule_evaluators:
            if condition_eval is None:
                # No condition (default rule) or simple formula
                try:
                    return formula_eval.evaluate(scores, entity_context)
                except FormulaError:
                    continue

            # Evaluate condition
            try:
                result = condition_eval.evaluate({}, entity_context)
                if result:  # Truthy
                    return formula_eval.evaluate(scores, entity_context)
            except FormulaError:
                continue

        return None


class LabelFunctionEvaluator:
    """Evaluator for label functions that directly return rank labels.

    This evaluator allows writing Python-like code that directly returns
    a label string, bypassing the numeric value + thresholds approach.

    Supports:
    - if/elif/else statements
    - return statements with string literals or expressions
    - Comparison operators (==, !=, <, <=, >, >=, in, not in)
    - Boolean operators (and, or, not)
    - Arithmetic operators (+, -, *, /, etc.)
    - entity.* attribute access
    - Score variable access
    - Safe functions (min, max, abs, avg, len, str, etc.)

    Example:
        evaluator = LabelFunctionEvaluator(
            label_function='''
if security >= 90 and testing >= 90:
    return 'S'
elif entity.lifecycle == 'experimental':
    return 'Experimental'
elif 'critical' in entity.tags and security < 80:
    return 'Critical Risk'
else:
    return 'B'
            ''',
            score_refs=["security", "testing"],
            entity_refs=["lifecycle", "tags"]
        )
        result = evaluator.evaluate(scores, entity_context)  # Returns label string
    """

    MAX_DEPTH = 50
    MAX_CODE_LENGTH = 20000
    MAX_STATEMENTS = 100

    def __init__(
        self,
        label_function: str,
        score_refs: list[str] | None = None,
        entity_refs: list[str] | None = None,
    ):
        """Initialize with label function code.

        Args:
            label_function: Python code with if/elif/else and return statements
            score_refs: List of allowed score variable names
            entity_refs: List of entity attributes that may be referenced

        Raises:
            FormulaError: If code is invalid or uses disallowed operations
        """
        if len(label_function) > self.MAX_CODE_LENGTH:
            raise FormulaError(f"Label function too long (max {self.MAX_CODE_LENGTH} chars)")

        self.label_function = label_function
        self.score_refs = set(score_refs or [])
        self.entity_refs = set(entity_refs or [])
        self._functions = SAFE_FUNCTIONS_EXTENDED
        self._local_vars: set[str] = set()  # Track local variables defined in code
        self._ast = self._parse_and_validate(label_function)

    def _parse_and_validate(self, code: str) -> ast.Module:
        """Parse code and validate it only uses allowed operations."""
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            raise FormulaError(f"Invalid syntax: {e}") from e

        if len(tree.body) > self.MAX_STATEMENTS:
            raise FormulaError(f"Too many statements (max {self.MAX_STATEMENTS})")

        self._validate_statements(tree.body, depth=0)
        return tree

    def _validate_statements(self, stmts: list[ast.stmt], depth: int) -> None:
        """Validate a list of statements."""
        if depth > self.MAX_DEPTH:
            raise FormulaError("Code is too complex (max depth exceeded)")

        for stmt in stmts:
            self._validate_statement(stmt, depth)

    def _validate_statement(self, stmt: ast.stmt, depth: int) -> None:
        """Validate a single statement."""
        if isinstance(stmt, ast.If):
            # if/elif/else
            self._validate_expr(stmt.test, depth + 1)
            self._validate_statements(stmt.body, depth + 1)
            self._validate_statements(stmt.orelse, depth + 1)

        elif isinstance(stmt, ast.Return):
            # return statement
            if stmt.value is not None:
                self._validate_expr(stmt.value, depth + 1)

        elif isinstance(stmt, ast.Assign):
            # Simple variable assignment (e.g., total = security * 0.4 + testing * 0.6)
            # Only allow single target, simple name (no tuple unpacking, no attribute assignment)
            if len(stmt.targets) != 1:
                raise FormulaError("Multiple assignment targets not allowed")
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                raise FormulaError("Only simple variable assignment allowed")
            # Track the local variable for validation
            self._local_vars.add(target.id)
            # Validate the value expression
            self._validate_expr(stmt.value, depth + 1)

        elif isinstance(stmt, ast.Expr):
            # Expression statement (usually not needed but allowed)
            self._validate_expr(stmt.value, depth + 1)

        elif isinstance(stmt, ast.Pass):
            # pass is allowed
            pass

        else:
            raise FormulaError(f"Statement type not allowed: {type(stmt).__name__}")

    def _validate_expr(self, node: ast.expr, depth: int) -> None:
        """Validate an expression node."""
        if depth > self.MAX_DEPTH:
            raise FormulaError("Expression is too complex (max depth exceeded)")

        if isinstance(node, ast.Constant):
            # Allow numeric, string, bool, and None constants
            if not isinstance(node.value, (int, float, str, bool, type(None))):
                raise FormulaError(f"Constant type not allowed: {type(node.value).__name__}")

        elif isinstance(node, ast.Name):
            # Allow score refs, function names, 'entity', local vars, and built-in constants
            if (node.id not in self.score_refs and
                node.id not in self._functions and
                node.id not in self._local_vars and
                node.id not in ("entity", "True", "False", "None")):
                raise FormulaError(f"Unknown variable: {node.id}")

        elif isinstance(node, ast.Attribute):
            # Only allow entity.attr access
            if isinstance(node.value, ast.Name) and node.value.id == "entity":
                if node.attr not in ALLOWED_ENTITY_ATTRS:
                    raise FormulaError(f"Entity attribute not allowed: entity.{node.attr}")
            else:
                raise FormulaError("Only entity.attribute access is allowed")

        elif isinstance(node, ast.BinOp):
            if type(node.op) not in SAFE_BINARY_OPS:
                raise FormulaError(f"Operator not allowed: {type(node.op).__name__}")
            self._validate_expr(node.left, depth + 1)
            self._validate_expr(node.right, depth + 1)

        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in SAFE_UNARY_OPS and not isinstance(node.op, ast.Not):
                raise FormulaError(f"Unary operator not allowed: {type(node.op).__name__}")
            self._validate_expr(node.operand, depth + 1)

        elif isinstance(node, ast.BoolOp):
            # and, or
            for value in node.values:
                self._validate_expr(value, depth + 1)

        elif isinstance(node, ast.Compare):
            # Allow comparison operators including 'in' and 'not in'
            for op in node.ops:
                if type(op) not in SAFE_COMPARE_OPS and not isinstance(op, (ast.In, ast.NotIn)):
                    raise FormulaError(f"Comparison operator not allowed: {type(op).__name__}")
            self._validate_expr(node.left, depth + 1)
            for comparator in node.comparators:
                self._validate_expr(comparator, depth + 1)

        elif isinstance(node, ast.IfExp):
            # Ternary expression
            self._validate_expr(node.test, depth + 1)
            self._validate_expr(node.body, depth + 1)
            self._validate_expr(node.orelse, depth + 1)

        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FormulaError("Only simple function calls allowed")
            if node.func.id not in self._functions:
                raise FormulaError(f"Function not allowed: {node.func.id}")
            if node.keywords:
                raise FormulaError("Keyword arguments not allowed")
            for arg in node.args:
                self._validate_expr(arg, depth + 1)

        elif isinstance(node, ast.Tuple | ast.List):
            for elt in node.elts:
                self._validate_expr(elt, depth + 1)

        elif isinstance(node, ast.Subscript):
            # Allow subscript for list/dict access (e.g., tags[0])
            self._validate_expr(node.value, depth + 1)
            self._validate_expr(node.slice, depth + 1)

        else:
            raise FormulaError(f"Expression type not allowed: {type(node).__name__}")

    def evaluate(
        self,
        scores: dict[str, float] | None = None,
        entity_context: EntityContext | None = None,
    ) -> str | None:
        """Evaluate the label function.

        Args:
            scores: Dictionary mapping score IDs to their values
            entity_context: Entity context for entity.* access

        Returns:
            Label string, or None if no return statement executed

        Raises:
            FormulaError: If evaluation fails
        """
        scores = scores or {}

        # Check required scores
        if self.score_refs:
            missing = self.score_refs - set(scores.keys())
            if missing:
                raise FormulaError(f"Missing required scores: {', '.join(sorted(missing))}")

        # Build context
        context: dict[str, Any] = {**scores, **self._functions}
        if entity_context:
            context["entity"] = entity_context

        try:
            return self._exec_statements(self._ast.body, context)
        except ReturnValue as rv:
            return rv.value
        except Exception as e:
            raise FormulaError(f"Evaluation failed: {e}") from e

    def _exec_statements(self, stmts: list[ast.stmt], context: dict[str, Any]) -> str | None:
        """Execute a list of statements."""
        for stmt in stmts:
            result = self._exec_statement(stmt, context)
            if result is not None:
                return result
        return None

    def _exec_statement(self, stmt: ast.stmt, context: dict[str, Any]) -> str | None:
        """Execute a single statement."""
        if isinstance(stmt, ast.If):
            # if/elif/else
            test_result = self._eval_expr(stmt.test, context)
            if test_result:
                return self._exec_statements(stmt.body, context)
            else:
                return self._exec_statements(stmt.orelse, context)

        elif isinstance(stmt, ast.Return):
            if stmt.value is not None:
                result = self._eval_expr(stmt.value, context)
                # Convert to string if not already
                if result is not None:
                    return str(result)
            return None

        elif isinstance(stmt, ast.Assign):
            # Variable assignment - store result in context
            # Already validated to be single target, simple name
            target = stmt.targets[0]
            assert isinstance(target, ast.Name)
            value = self._eval_expr(stmt.value, context)
            context[target.id] = value
            return None

        elif isinstance(stmt, ast.Expr):
            # Expression statement - evaluate but don't return
            self._eval_expr(stmt.value, context)
            return None

        elif isinstance(stmt, ast.Pass):
            return None

        return None

    def _eval_expr(self, node: ast.expr, context: dict[str, Any]) -> Any:
        """Evaluate an expression node."""
        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            if node.id == "True":
                return True
            elif node.id == "False":
                return False
            elif node.id == "None":
                return None
            value = context.get(node.id)
            return value

        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "entity":
                entity = context.get("entity")
                if entity is None:
                    return None
                return getattr(entity, node.attr, None)
            raise FormulaError("Only entity.attribute access is allowed")

        elif isinstance(node, ast.BinOp):
            left = self._eval_expr(node.left, context)
            right = self._eval_expr(node.right, context)
            op_func = SAFE_BINARY_OPS[type(node.op)]
            return op_func(left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_expr(node.operand, context)
            if isinstance(node.op, ast.Not):
                return not operand
            op_func = SAFE_UNARY_OPS[type(node.op)]
            return op_func(operand)

        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._eval_expr(value, context):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_expr(value, context):
                        return True
                return False

        elif isinstance(node, ast.Compare):
            left = self._eval_expr(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_expr(comparator, context)
                if isinstance(op, ast.In):
                    if left not in (right or []):
                        return False
                elif isinstance(op, ast.NotIn):
                    if left in (right or []):
                        return False
                else:
                    op_func = SAFE_COMPARE_OPS[type(op)]
                    if not op_func(left, right):
                        return False
                left = right
            return True

        elif isinstance(node, ast.IfExp):
            test_result = self._eval_expr(node.test, context)
            if test_result:
                return self._eval_expr(node.body, context)
            else:
                return self._eval_expr(node.orelse, context)

        elif isinstance(node, ast.Call):
            func = context[node.func.id]
            args = [self._eval_expr(arg, context) for arg in node.args]
            return func(*args)

        elif isinstance(node, ast.Tuple | ast.List):
            return [self._eval_expr(elt, context) for elt in node.elts]

        elif isinstance(node, ast.Subscript):
            value = self._eval_expr(node.value, context)
            index = self._eval_expr(node.slice, context)
            if value is None:
                return None
            try:
                return value[index]
            except (IndexError, KeyError, TypeError):
                return None

        raise FormulaError(f"Cannot evaluate expression: {type(node).__name__}")


class ReturnValue(Exception):
    """Internal exception to propagate return values."""

    def __init__(self, value: str | None):
        self.value = value
