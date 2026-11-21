"""Lectura tolerante de un objeto JSON que aún se está generando.

El modelo emite el registro token a token; para mostrar cómo se llena la plantilla
se interpreta el texto parcial cerrando lo que quedó abierto y descartando el
último valor incompleto.
"""

import json
from typing import Any


def parse_partial_json_object(text: str) -> dict[str, Any] | None:
    """El objeto JSON más completo que se puede leer de ``text``, o ``None`` si no hay ninguno."""
    start = text.find("{")
    if start == -1:
        return None
    body = text[start:]

    stack: list[str] = []
    cut_points: list[tuple[int, str]] = []
    in_string = escaped = False
    end = len(body)
    for index, char in enumerate(body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
            cut_points.append((index + 1, "".join(reversed(stack))))
        elif char in "}]":
            stack.pop()
            if not stack:
                end = index + 1
                break
        elif char == ",":
            cut_points.append((index, "".join(reversed(stack))))

    candidates = [(end, "".join(reversed(stack)), in_string)]
    candidates += [(position, closers, False) for position, closers in reversed(cut_points)]
    for position, closers, open_string in candidates:
        parsed = _load(body[:position] + ('"' if open_string else "") + closers)
        if parsed is not None:
            return parsed
    return None


def _load(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
