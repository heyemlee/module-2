"""Safe formula evaluator: correctness on decomposition expressions + safety."""

import pytest

from app.formula import FormulaError, evaluate


def test_arithmetic_matches_python():
    ns = {"W": 762.0, "D": 609.6, "H": 876.3, "t": 18.0, "g": 3.0, "eb": 1.0}
    assert evaluate("W - 2*t", ns) == 762.0 - 2 * 18.0
    assert evaluate("W - 2*t + 2*g", ns) == 762.0 - 2 * 18.0 + 2 * 3.0
    assert evaluate("D - t - eb", ns) == 609.6 - 18.0 - 1.0
    assert evaluate("H", ns) == 876.3


def test_unary_and_parentheses():
    assert evaluate("-(3 - 5)", {}) == 2.0
    assert evaluate("2 * (3 + 4)", {}) == 14.0


def test_unknown_variable_raises():
    with pytest.raises(FormulaError):
        evaluate("W - q", {"W": 10.0})


def test_no_arbitrary_code_execution():
    # names that aren't in the namespace are rejected; calls/attributes never parse-eval
    with pytest.raises(FormulaError):
        evaluate("__import__('os').system('echo hi')", {})
    with pytest.raises(FormulaError):
        evaluate("W ** 2", {"W": 3.0})  # power operator not whitelisted
