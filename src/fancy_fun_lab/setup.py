"""``SetupValidator``: what ``setup()`` accepts, with the PHP messages verbatim."""

from __future__ import annotations

from typing import Any

from .errors import FunLabError

#: canonical type -> accepted aliases (the canonical name is always accepted).
VALID_TYPES: dict[str, list[str]] = {
    "achievement": ["achievement"],
    "gamed-metric": ["gamed-metric", "metric"],
    "metric-level": ["metric-level", "level"],
    "metric-level-group": ["metric-level-group", "group"],
    "metric-level-group-level": ["metric-level-group-level", "group-level"],
    "metric-level-group-metric": ["metric-level-group-metric", "group-metric"],
    "prize": ["prize"],
}

#: type -> field -> (required, type expression), in the PHP order (messages list them so).
RULES: dict[str, dict[str, tuple[bool, str]]] = {
    "achievement": {
        "slug": (True, "string"),
        "name": (False, "string"),
        "description": (False, "string"),
        "icon": (False, "string"),
        "for": (False, "string"),
        "metadata": (False, "array"),
        "active": (False, "bool"),
        "hidden": (False, "bool"),
        "order": (False, "int"),
    },
    "gamed-metric": {
        "slug": (True, "string"),
        "name": (False, "string"),
        "description": (False, "string"),
        "icon": (False, "string"),
        "active": (False, "bool"),
    },
    "metric-level": {
        "metric": (True, "string"),
        "level": (True, "int"),
        "xp": (True, "int"),
        "name": (False, "string"),
        "description": (False, "string"),
    },
    "metric-level-group": {
        "slug": (True, "string"),
        "name": (False, "string"),
        "description": (False, "string"),
    },
    "metric-level-group-level": {
        "group": (True, "string"),
        "level": (True, "int"),
        "xp": (True, "int"),
        "name": (False, "string"),
        "description": (False, "string"),
    },
    "metric-level-group-metric": {
        "group": (True, "string"),
        "metric": (True, "string"),
        "weight": (False, "float"),
    },
    "prize": {
        "slug": (True, "string"),
        "name": (False, "string"),
        "description": (False, "string"),
        "type": (False, "string"),
        "cost": (False, "int|float"),
        "inventory": (False, "int"),
        "metadata": (False, "array"),
        "active": (False, "bool"),
        "order": (False, "int"),
    },
}


def normalize_type(kind: str) -> str:
    for canonical, aliases in VALID_TYPES.items():
        if kind == canonical or kind in aliases:
            return canonical
    return kind


def _php_type(value: Any) -> str:
    # bool before int: in Python True is an int, in PHP it is not.
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, dict | list):
        return "array"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return type(value).__name__


def _compatible(actual: str, expected: str) -> bool:
    if "|" in expected:
        return any(_compatible(actual, e.strip()) for e in expected.split("|"))
    return actual == expected or (expected == "float" and actual == "int")


def validate(kind: str, with_: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_type(kind)
    if normalized not in RULES:
        raise FunLabError(f"Unknown entity type '{kind}'. Valid types: {', '.join(VALID_TYPES)}")
    rules = RULES[normalized]
    unknown = [f for f in with_ if f not in rules]
    if unknown:
        raise FunLabError(
            f"LFL::setup('{normalized}'): Unknown field(s): {', '.join(unknown)}. "
            f"Valid fields: {', '.join(rules)}"
        )
    for field, (required, _) in rules.items():
        if required and field not in with_:
            raise FunLabError(f"LFL::setup('{normalized}') requires '{field}' in the 'with' array")
    for field, value in with_.items():
        required, expected = rules[field]
        if value is None and not required:
            continue
        actual = _php_type(value)
        if not _compatible(actual, expected):
            raise FunLabError(
                f"LFL::setup('{normalized}'): '{field}' must be {expected}, {actual} given"
            )
    return with_
