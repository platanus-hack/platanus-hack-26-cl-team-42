"""Ninja API for the eventcore documentation graph.

Mount on the shared API::

    from eventcore.contrib.docs import router
    api.add_router("/eventcore", router)

Full path: ``/{URL_PREFIX}/api/eventcore/graph``.
"""

from __future__ import annotations

from typing import Any

from ninja import Router, Schema

from eventcore.introspection import build_graph

router = Router(tags=["eventcore-docs"])


class SourceOut(Schema):
    file: str | None = None
    file_relative: str | None = None
    line: int | None = None
    end_line: int | None = None
    vscode_url: str | None = None
    cursor_url: str | None = None
    preview: str | None = None
    preview_truncated: bool = False


class FieldOut(Schema):
    name: str
    type: str
    required: bool
    default: Any | None = None


class NodeOut(Schema):
    id: str
    kind: str
    name: str
    doc: str = ""
    module: str = ""
    app: str = ""
    fields: list[FieldOut] = []
    errors: list[str] = []
    target_model: str | None = None
    subscribed_to: str | None = None
    subscribed_to_module: str | None = None
    qualname: str | None = None
    applies_events: list[str] = []
    invokes_commands: list[str] = []
    is_entry: bool = False
    source: SourceOut


class EdgeOut(Schema):
    id: str
    source: str
    target: str
    kind: str
    subscribed_to: str | None = None
    unresolved: bool = False


class OrphansOut(Schema):
    events_never_applied: list[str]
    events_without_policies: list[str]
    commands_without_events: list[str]
    policies_without_matching_messages: list[str]


class FlowOut(Schema):
    apps: list[str]
    entry_command_ids: list[str]
    commands_by_app: dict[str, list[str]]
    event_applied_by: dict[str, list[str]]
    event_policies: dict[str, list[str]]
    event_unlocks_commands: dict[str, list[str]] = {}
    policy_invokes_commands: dict[str, list[str]] = {}
    next_commands: dict[str, list[str]]


class GraphOut(Schema):
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    orphans: OrphansOut
    flow: FlowOut


@router.get("/graph", response=GraphOut)
def get_graph(request):
    """Live graph of commands → events → policies (project-agnostic)."""
    return build_graph()
