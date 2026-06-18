"""Safe arithmetic evaluator for rules-as-data decomposition formulas.

Cabinet part dimensions live in YAML as expressions like ``"W - 2*t + 2*g"`` over a
fixed namespace (cabinet W/D/H, vr, and named constants). This evaluates them with a
whitelisted AST — only numbers, those names, ``+ - * /`` and parentheses — so a rules
file can never execute arbitrary code. Anything else raises ``FormulaError``.
"""

import ast
import operator

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class FormulaError(ValueError):
    """A decomposition formula is malformed or references an unknown variable."""


def evaluate(expr: str, variables: dict[str, float]) -> float:
    """Evaluate ``expr`` against ``variables`` (e.g. {'W': 762.0, 't': 18.0})."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise FormulaError(f"cannot parse formula '{expr}': {exc}") from exc
    return _eval(tree.body, variables, expr)


def _eval(node: ast.AST, variables: dict[str, float], expr: str) -> float:
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval(node.left, variables, expr)
        right = _eval(node.right, variables, expr)
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, variables, expr))
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        raise FormulaError(f"unknown variable '{node.id}' in formula '{expr}'")
    raise FormulaError(f"unsupported expression in formula '{expr}'")
