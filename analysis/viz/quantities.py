"""A number that carries its formula, its inputs and where each one came from.

This is the primitive behind the "all explainable values" requirement: a run
page never shows a bare number. It shows the number, the symbolic formula, the
same formula with every symbol replaced by its actual value, and a row per
input naming its origin.

assert_consistent() evaluates formula_py against the declared inputs and checks
it reproduces `value`. It runs in the test suite and in --verify, which makes
it structurally impossible for a displayed formula to be a lie.
"""
from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field

# Origin strings name exactly where a value came from. Examples:
#   root:DetectorHistogrammer/eiger2_detector/event_size_clusters#sum
#   conf:phase2_selection/p2_bare_eiger2_40keV.conf#Allpix.number_of_events
#   manifest:phase2_selection_run_manifest.csv#output_name=...,col=n_events
#   const:material_penetration_experiment.EPSILON_CDTE_EV
#   csv:analysis/results/material_penetration_uniform/cdte_interaction.csv#E=40
#   run:p2_bare_eiger2_60keV#detection_efficiency
#   derived:this_page#window_fraction
Origin = str


@dataclass(frozen=True)
class QRef:
    """One input to a formula."""

    name: str                # the symbol used in formula_py
    value: float
    unit: str = ""
    origin: Origin = ""
    label: str = ""
    hist_key: str | None = None   # anchor target on the page, when it is a histogram

    @property
    def display(self) -> str:
        return self.label or self.name


def _fmt(x: float) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        if x == int(x) and abs(x) < 1e15:
            return f"{int(x):,}"
        if abs(x) >= 1e6 or (x != 0 and abs(x) < 1e-4):
            return f"{x:.6g}"
        return f"{x:.6g}"
    return str(x)


class _Substituter(ast.NodeTransformer):
    """Replace Name nodes with their numeric values.

    Uses the AST rather than string replacement on purpose: a plain
    str.replace would corrupt overlapping symbols (n_events is a substring of
    n_events_default).
    """

    def __init__(self, values: dict[str, float]):
        self.values = values

    def visit_Name(self, node: ast.Name):  # noqa: N802
        if node.id in self.values:
            return ast.Constant(value=self.values[node.id])
        return node


class _Renderer(ast.NodeVisitor):
    """Unparse an AST, printing numeric constants in a human format."""

    _OPS = {ast.Add: "+", ast.Sub: "−", ast.Mult: "×", ast.Div: "/",
            ast.Pow: "^", ast.Mod: "mod"}

    def visit_Constant(self, node):  # noqa: N802
        return _fmt(node.value)

    def visit_Name(self, node):  # noqa: N802
        return node.id

    def visit_BinOp(self, node):  # noqa: N802
        op = self._OPS.get(type(node.op), "?")
        return f"{self.visit(node.left)} {op} {self.visit(node.right)}"

    def visit_UnaryOp(self, node):  # noqa: N802
        return f"-{self.visit(node.operand)}"

    def visit_Call(self, node):  # noqa: N802
        fn = node.func.id if isinstance(node.func, ast.Name) else "f"
        return f"{fn}(" + ", ".join(self.visit(a) for a in node.args) + ")"

    def generic_visit(self, node):
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        return ast.unparse(node)


_SAFE = {
    "min": min, "max": max, "abs": abs,
    "log": math.log, "exp": math.exp, "sqrt": math.sqrt, "nan": math.nan,
}


@dataclass(frozen=True)
class Quantity:
    key: str
    label: str
    value: float
    unit: str = ""
    formula_tex: str = ""
    formula_py: str = ""
    inputs: tuple[QRef, ...] = ()
    note: str = ""
    valid: bool = True
    upstream_runs: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default=())

    @property
    def input_values(self) -> dict[str, float]:
        return {q.name: q.value for q in self.inputs}

    def substituted(self) -> str:
        """The formula with every symbol replaced by its value, then the result.

        This is the single most load-bearing method on the page: it is what
        lets a reader check the arithmetic by eye instead of trusting it.
        """
        if not self.formula_py:
            return ""
        try:
            tree = ast.parse(self.formula_py, mode="eval")
            subbed = _Substituter(self.input_values).visit(tree)
            ast.fix_missing_locations(subbed)
            lhs = _Renderer().visit(subbed.body)
        except Exception:
            return ""
        return f"{lhs} = {_fmt(self.value)}"

    def evaluate(self) -> float:
        tree = ast.parse(self.formula_py, mode="eval")
        return float(eval(compile(tree, "<formula>", "eval"),  # noqa: S307
                          {"__builtins__": {}}, {**_SAFE, **self.input_values}))

    def assert_consistent(self, rtol: float = 1e-9) -> None:
        """Fail if the displayed formula does not reproduce the displayed value."""
        if not self.formula_py:
            return
        got = self.evaluate()
        if math.isnan(got) and math.isnan(self.value):
            return
        if not math.isclose(got, self.value, rel_tol=rtol, abs_tol=1e-12):
            raise AssertionError(
                f"{self.key}: formula {self.formula_py!r} evaluates to {got!r} "
                f"but the reported value is {self.value!r}"
            )

    def is_consistent(self, rtol: float = 1e-9) -> bool:
        try:
            self.assert_consistent(rtol)
            return True
        except Exception:
            return False
