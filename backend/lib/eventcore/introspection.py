"""Build a documentation graph of commands, events, and policies.

The graph is derived at runtime from:

* :func:`registered_commands` / :func:`registered_events`
* AST of each command's ``perform`` (``apply_event(..., SomeEvent(...))``)
* :func:`registered_subscriptions` (``eventcore.on`` policies)
* AST of each policy handler for ``invoke(SomeCommand(...))`` cascades

It is intentionally read-only documentation — not used to drive dispatch.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .commands import Command, CommandError, registered_commands
from .events import Event, ModelEvent, registered_events
from .registry import registered_subscriptions

# Framework bases excluded from "orphan" / catalog noise.
_FRAMEWORK_EVENT_NAMES = frozenset({"Event", "ModelEvent"})
_FRAMEWORK_COMMAND_NAMES = frozenset({"Command"})


def build_graph() -> dict[str, Any]:
    """Return a JSON-serializable graph of the live eventcore wiring."""
    commands = [c for c in registered_commands() if c.__name__ not in _FRAMEWORK_COMMAND_NAMES]
    events = [e for e in registered_events() if e.__name__ not in _FRAMEWORK_EVENT_NAMES]

    command_nodes = [_command_node(c) for c in commands]
    event_nodes = [_event_node(e) for e in events]

    applies_edges: list[dict[str, Any]] = []
    applied_by: dict[str, set[str]] = {e.__name__: set() for e in events}
    for command in commands:
        for event_name in _events_applied_in_perform(command):
            applies_edges.append(
                {
                    "id": f"applies:{command.__name__}:{event_name}",
                    "source": f"command:{command.__name__}",
                    "target": f"event:{event_name}",
                    "kind": "applies",
                }
            )
            if event_name in applied_by:
                applied_by[event_name].add(command.__name__)

    policy_nodes: list[dict[str, Any]] = []
    policy_edges: list[dict[str, Any]] = []
    invoke_edges: list[dict[str, Any]] = []
    policy_invokes: dict[str, list[str]] = {}
    seen_policies: set[str] = set()
    event_by_name = {e.__name__: e for e in events}
    command_names = {c.__name__ for c in commands}

    for message_type, handler in registered_subscriptions():
        policy = _policy_node(message_type, handler)
        if policy["id"] not in seen_policies:
            invoked = [
                name
                for name in _commands_invoked_in_handler(handler)
                if name in command_names
            ]
            policy["invokes_commands"] = invoked
            policy_nodes.append(policy)
            seen_policies.add(policy["id"])
            cmd_ids = [f"command:{name}" for name in invoked]
            policy_invokes[policy["id"]] = cmd_ids
            for name in invoked:
                invoke_edges.append(
                    {
                        "id": f"invokes:{policy['id']}:{name}",
                        "source": policy["id"],
                        "target": f"command:{name}",
                        "kind": "invokes",
                    }
                )

        # Edge from every concrete registered type that matches this subscription
        # via MRO (so on(ExpenseEvent) links to ExpenseRecorded, etc.).
        matched_event_names = [
            name
            for name, event_cls in event_by_name.items()
            if _type_matches_subscription(event_cls, message_type)
        ]
        matched_command_names = [
            c.__name__
            for c in commands
            if _type_matches_subscription(c, message_type)
        ]

        if matched_event_names or matched_command_names:
            for name in matched_event_names:
                policy_edges.append(
                    {
                        "id": f"policy:{name}:{policy['id']}",
                        "source": f"event:{name}",
                        "target": policy["id"],
                        "kind": "policy",
                        "subscribed_to": message_type.__name__,
                    }
                )
            for name in matched_command_names:
                policy_edges.append(
                    {
                        "id": f"policy-cmd:{name}:{policy['id']}",
                        "source": f"command:{name}",
                        "target": policy["id"],
                        "kind": "policy",
                        "subscribed_to": message_type.__name__,
                    }
                )
        else:
            # Subscription to a base/framework type with no concrete match yet.
            sub_id = f"subscription:{message_type.__name__}"
            policy_edges.append(
                {
                    "id": f"policy-sub:{sub_id}:{policy['id']}",
                    "source": sub_id,
                    "target": policy["id"],
                    "kind": "policy",
                    "subscribed_to": message_type.__name__,
                    "unresolved": True,
                }
            )

    events_with_policies = {
        edge["source"].removeprefix("event:")
        for edge in policy_edges
        if edge["source"].startswith("event:")
    }
    commands_that_apply = {edge["source"].removeprefix("command:") for edge in applies_edges}

    orphans = {
        "events_never_applied": sorted(
            name for name, cmds in applied_by.items() if not cmds
        ),
        "events_without_policies": sorted(
            e.__name__ for e in events if e.__name__ not in events_with_policies
        ),
        "commands_without_events": sorted(
            c.__name__ for c in commands if c.__name__ not in commands_that_apply
        ),
        "policies_without_matching_messages": sorted(
            {
                p["id"]
                for p in policy_nodes
                if not any(e["target"] == p["id"] and not e.get("unresolved") for e in policy_edges)
            }
        ),
    }

    # Progressive-flow helpers: entry commands + per-app / per-event indexes.
    for node in command_nodes:
        node["is_entry"] = _is_entry_command(node)

    commands_by_app: dict[str, list[str]] = {}
    for node in command_nodes:
        commands_by_app.setdefault(node["app"] or "other", []).append(node["id"])
    for app_cmds in commands_by_app.values():
        app_cmds.sort()

    event_policies: dict[str, list[str]] = {e.__name__: [] for e in events}
    for edge in policy_edges:
        if edge["source"].startswith("event:") and not edge.get("unresolved"):
            event_policies.setdefault(edge["source"].removeprefix("event:"), []).append(
                edge["target"]
            )

    # After running command C, suggest other commands in the same app
    # (follow-ups first: those that take entity ids).
    next_commands: dict[str, list[str]] = {}
    for node in command_nodes:
        same_app = [
            other
            for other in command_nodes
            if other["id"] != node["id"] and other["app"] == node["app"]
        ]
        same_app.sort(key=lambda n: (n["is_entry"], n["name"]))
        next_commands[node["id"]] = [n["id"] for n in same_app]

    # Heuristic: which follow-up commands typically need state this event helps create.
    event_unlocks: dict[str, list[str]] = {}
    unlock_edges: list[dict[str, Any]] = []
    for ev in event_nodes:
        unlocked = _commands_unlocked_by_event(ev, command_nodes, applied_by)
        event_unlocks[ev["name"]] = unlocked
        for cmd_id in unlocked:
            unlock_edges.append(
                {
                    "id": f"unlocks:{ev['name']}:{cmd_id}",
                    "source": ev["id"],
                    "target": cmd_id,
                    "kind": "unlocks",
                }
            )

    apps = sorted({n["app"] for n in command_nodes if n["app"]})

    return {
        "nodes": command_nodes + event_nodes + policy_nodes,
        "edges": applies_edges + policy_edges + unlock_edges + invoke_edges,
        "orphans": orphans,
        "flow": {
            "apps": apps,
            "entry_command_ids": sorted(
                n["id"] for n in command_nodes if n["is_entry"]
            ),
            "commands_by_app": commands_by_app,
            "event_applied_by": {k: sorted(v) for k, v in applied_by.items()},
            "event_policies": {k: sorted(set(v)) for k, v in event_policies.items()},
            "event_unlocks_commands": event_unlocks,
            "policy_invokes_commands": policy_invokes,
            "next_commands": next_commands,
        },
    }


def _is_entry_command(node: dict[str, Any]) -> bool:
    """Heuristic: creators / starts — no required ``*_id`` besides ``actor_id``.

    Examples: ``PlaceOrder``, ``CreateHousehold``, ``CreateShoppingList``.
    Follow-ups like ``ShipOrder(order_id=…)`` or ``SetExpenseSettled(expense_id=…)``
    are not entry points.
    """
    for field in node.get("fields") or []:
        name = field.get("name") or ""
        if not field.get("required"):
            continue
        if name in {"actor_id"}:
            continue
        if name.endswith("_id"):
            return False
    return True


def _id_fields_for_model(model_name: str) -> tuple[str, ...]:
    """Map ``Order`` → ``order_id``, ``FixedExpense`` → ``fixed_expense_id`` / ``fixed_id``."""
    import re

    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", model_name).lower()
    fields = [f"{snake}_id"]
    parts = snake.split("_")
    if len(parts) > 1:
        fields.append(f"{parts[0]}_id")
    return tuple(dict.fromkeys(fields))


def _commands_unlocked_by_event(
    event_node: dict[str, Any],
    command_nodes: list[dict[str, Any]],
    applied_by: dict[str, set[str]],
) -> list[str]:
    """Commands that usually become meaningful after this event's state exists.

    Not a hard gate in eventcore — a documentation heuristic:

    * required ``*_id`` matching the event's target model
    * same-app non-entry follow-ups
    * invite-style entry commands (``email`` field) after ``*Created`` events
    """
    appliers = applied_by.get(event_node["name"], set())
    app = event_node.get("app") or ""
    model = event_node.get("target_model")
    id_fields = set(_id_fields_for_model(model)) if model else set()
    created = event_node["name"].endswith("Created")
    unlocked: list[str] = []

    for cmd in command_nodes:
        if (cmd.get("app") or "") != app:
            continue
        if cmd["name"] in appliers:
            continue
        field_names = {f.get("name") for f in (cmd.get("fields") or [])}
        required = {
            f.get("name")
            for f in (cmd.get("fields") or [])
            if f.get("required")
        }
        if id_fields & field_names:
            unlocked.append(cmd["id"])
            continue
        if not cmd.get("is_entry"):
            unlocked.append(cmd["id"])
            continue
        if created and ("email" in field_names or "display_name" in required):
            unlocked.append(cmd["id"])
            continue
    return sorted(set(unlocked))


def _command_node(command: type[Command]) -> dict[str, Any]:
    return {
        "id": f"command:{command.__name__}",
        "kind": "command",
        "name": command.__name__,
        "doc": (command.__doc__ or "").strip(),
        "module": command.__module__,
        "app": _app_label(command.__module__),
        "fields": _fields(command),
        "errors": _command_errors(command),
        "source": _source_info(command),
        "applies_events": _events_applied_in_perform(command),
        "is_entry": False,  # filled in build_graph
    }


def _event_node(event: type[Event]) -> dict[str, Any]:
    return {
        "id": f"event:{event.__name__}",
        "kind": "event",
        "name": event.__name__,
        "doc": (event.__doc__ or "").strip(),
        "module": event.__module__,
        "app": _app_label(event.__module__),
        "fields": _fields(event),
        "target_model": _event_target_model(event),
        "source": _source_info(event),
    }


def _policy_node(message_type: type, handler: Callable[..., Any]) -> dict[str, Any]:
    source = _source_info(handler)
    qualname = getattr(handler, "__qualname__", getattr(handler, "__name__", repr(handler)))
    module = getattr(handler, "__module__", "")
    node_id = f"policy:{module}.{qualname}:{source.get('line') or 0}"
    return {
        "id": node_id,
        "kind": "policy",
        "name": qualname.split(".")[-1],
        "qualname": qualname,
        "doc": (inspect.getdoc(handler) or "").strip(),
        "module": module,
        "app": _app_label(module),
        "subscribed_to": message_type.__name__,
        "subscribed_to_module": getattr(message_type, "__module__", ""),
        "invokes_commands": [],
        "source": source,
    }


def _events_applied_in_perform(command: type[Command]) -> list[str]:
    """Statically find ``SomeEvent`` names passed to ``apply_event`` in ``perform``."""
    perform = getattr(command, "perform", None)
    if perform is None:
        return []
    try:
        source = textwrap.dedent(inspect.getsource(perform))
    except (OSError, TypeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_apply_event_call(node):
            continue
        event_name = _event_name_from_apply_call(node)
        if event_name and event_name not in found:
            found.append(event_name)
    return found


def _commands_invoked_in_handler(handler: Callable[..., Any]) -> list[str]:
    """Statically find ``SomeCommand`` names passed to ``invoke`` in a policy."""
    try:
        source = textwrap.dedent(inspect.getsource(handler))
    except (OSError, TypeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_invoke_call(node):
            continue
        command_name = _command_name_from_invoke_call(node)
        if command_name and command_name not in found:
            found.append(command_name)
    return found


def _is_apply_event_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "apply_event"
    if isinstance(func, ast.Attribute):
        return func.attr == "apply_event"
    return False


def _is_invoke_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "invoke"
    if isinstance(func, ast.Attribute):
        return func.attr == "invoke"
    return False


def _event_name_from_apply_call(node: ast.Call) -> str | None:
    event_node: ast.AST | None = None
    if len(node.args) >= 2:
        event_node = node.args[1]
    for keyword in node.keywords:
        if keyword.arg in {"event", "evt"}:
            event_node = keyword.value
    if event_node is None:
        return None
    if isinstance(event_node, ast.Call):
        return _name_of(event_node.func)
    if isinstance(event_node, (ast.Name, ast.Attribute)):
        return _name_of(event_node)
    return None


def _command_name_from_invoke_call(node: ast.Call) -> str | None:
    command_node: ast.AST | None = None
    if node.args:
        command_node = node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "command":
            command_node = keyword.value
    if command_node is None:
        return None
    if isinstance(command_node, ast.Call):
        return _name_of(command_node.func)
    if isinstance(command_node, (ast.Name, ast.Attribute)):
        return _name_of(command_node)
    return None


def _name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _type_matches_subscription(concrete: type, subscribed: type) -> bool:
    try:
        return issubclass(concrete, subscribed)
    except TypeError:
        return False


def _app_label(module: str) -> str:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "apps":
        return parts[1]
    if parts and parts[0] == "eventcore":
        return "eventcore"
    return parts[0] if parts else ""


def _source_info(obj: Any) -> dict[str, Any]:
    empty = {
        "file": None,
        "file_relative": None,
        "line": None,
        "end_line": None,
        "vscode_url": None,
        "cursor_url": None,
        "preview": None,
        "preview_truncated": False,
    }
    try:
        path = inspect.getfile(obj)
        lines, start = inspect.getsourcelines(obj)
        end = start + len(lines) - 1
    except (TypeError, OSError):
        return empty

    relative = _relative_path(path)
    editor_path = _editor_filesystem_path(path, relative)
    preview, truncated = _source_preview(lines)
    # Absolute Unix paths become vscode://file//Users/... (two slashes after file:)
    return {
        "file": editor_path,
        "file_relative": relative,
        "line": start,
        "end_line": end,
        "vscode_url": f"vscode://file/{editor_path}:{start}",
        "cursor_url": f"cursor://file/{editor_path}:{start}",
        "preview": preview,
        "preview_truncated": truncated,
    }


_PREVIEW_MAX_LINES = 80


def _source_preview(lines: list[str]) -> tuple[str | None, bool]:
    """Return a truncated source snippet for the docs UI (no IDE required)."""
    if not lines:
        return None, False
    truncated = len(lines) > _PREVIEW_MAX_LINES
    chunk = lines[:_PREVIEW_MAX_LINES]
    text = "".join(chunk).rstrip("\n")
    if truncated:
        text = f"{text}\n# … truncated ({len(lines)} lines total)"
    return text, truncated


def _editor_filesystem_path(runtime_path: str, relative: str | None) -> str:
    """Map a path inside the runtime (e.g. Docker ``/app/...``) to the host IDE path.

    Set ``EVENTCORE_DOCS_HOST_ROOT`` to the host directory that corresponds to
    Django ``BASE_DIR`` (the bind-mounted backend root). Without it, the
    runtime path is returned unchanged and editor links only work when the
    process already runs on the host.
    """
    host_root = _docs_host_root()
    if host_root is None:
        return runtime_path
    if relative:
        return str((host_root / relative).resolve())
    try:
        from django.conf import settings

        base = Path(settings.BASE_DIR).resolve()
        rel = Path(runtime_path).resolve().relative_to(base)
        return str((host_root / rel).resolve())
    except Exception:
        return runtime_path


def _docs_host_root() -> Path | None:
    """Resolve the host filesystem root that mirrors Django ``BASE_DIR``.

    Lookup order:

    1. ``EVENTCORE_DOCS_HOST_ROOT`` env / Django setting
    2. ``BASE_DIR/.eventcore-docs-host-root`` (written by ``just local up`` so
       Docker bind-mounts carry the host path without relying on compose env)
    """
    import os

    raw = os.environ.get("EVENTCORE_DOCS_HOST_ROOT", "").strip()
    if not raw:
        try:
            from django.conf import settings

            raw = str(getattr(settings, "EVENTCORE_DOCS_HOST_ROOT", "") or "").strip()
        except Exception:
            raw = ""

    if not raw:
        try:
            from django.conf import settings

            marker = Path(settings.BASE_DIR) / ".eventcore-docs-host-root"
            if marker.is_file():
                raw = marker.read_text(encoding="utf-8").strip()
        except Exception:
            raw = ""

    if not raw:
        # Last resort when code is not under Docker: runtime path is already host.
        try:
            from django.conf import settings

            base = Path(settings.BASE_DIR).resolve()
            if base.exists() and not str(base).startswith("/app"):
                return base
        except Exception:
            pass
        return None
    return Path(raw).expanduser()


def _relative_path(path: str) -> str:
    candidate = Path(path)
    for parent in [Path.cwd(), *Path.cwd().parents]:
        try:
            return str(candidate.resolve().relative_to(parent.resolve()))
        except ValueError:
            continue
    # Docker image layout: /app/...
    parts = candidate.parts
    if "app" in parts:
        idx = parts.index("app")
        return str(Path(*parts[idx + 1 :])) if idx + 1 < len(parts) else candidate.name
    return candidate.name


def _fields(model_cls: type) -> list[dict[str, Any]]:
    model_fields = getattr(model_cls, "model_fields", None)
    if not model_fields:
        return []
    return [
        {
            "name": name,
            "type": _type_name(field.annotation),
            "required": field.is_required(),
            "default": _field_default(field),
        }
        for name, field in model_fields.items()
        if not name.startswith("_")
    ]


def _field_default(field: FieldInfo) -> Any | None:
    if field.is_required() or field.default is PydanticUndefined:
        return None
    default = field.default
    if isinstance(default, (str, int, float, bool)) or default is None:
        return default
    return repr(default)


def _type_name(annotation: Any) -> str:
    if annotation is None:
        return "None"
    name = getattr(annotation, "__name__", None)
    if name:
        return name
    return str(annotation).replace("typing.", "")


def _command_errors(command_cls: type) -> list[str]:
    return sorted(
        attr.__name__
        for attr in vars(command_cls).values()
        if isinstance(attr, type) and issubclass(attr, CommandError)
    )


def _event_target_model(event_cls: type) -> str | None:
    for base in event_cls.__mro__:
        meta = getattr(base, "__pydantic_generic_metadata__", None)
        if meta and meta.get("origin") is ModelEvent and meta.get("args"):
            arg = meta["args"][0]
            return getattr(arg, "__name__", str(arg))
    return None
