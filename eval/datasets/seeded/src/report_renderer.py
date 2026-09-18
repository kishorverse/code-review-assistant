"""Render customer reports and evaluate the formulas in their cells."""

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("templates"), autoescape=False)


def render_report(name: str, context: dict[str, object]) -> str:
    """Render the named template with values supplied by the customer."""
    return env.get_template(name).render(**context)


def evaluate_formula(formula: str, values: dict[str, float]) -> float:
    """Compute a report cell from a formula such as ``revenue - cost``."""
    return float(eval(formula, {}, values))
