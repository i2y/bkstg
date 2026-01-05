"""Safe formula evaluator using AST parsing."""

import ast
import operator
from typing import Any


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
