"""Registro clínico y traspasos, montados en ``/-/api/episodes``.

Todo se calcula para el usuario activo: sus pacientes asignados y los traspasos que envió o
recibió.
"""

from typing import Any

from ninja import Router, Schema
from ninja.errors import HttpError

from . import episode_services as episodes

router = Router(tags=["episodes"])


class ChartIn(Schema):
    encounter_ids: list[str]


class HandoffIn(Schema):
    to_id: int
    note: str = ""
    snapshots: list[dict[str, Any]]


@router.get("/records", response=list[dict[str, Any]])
def list_records(request):
    """Un registro clínico por paciente asignado al profesional activo."""
    return episodes.episode_records(request.user)


@router.get("/team", response=dict[str, Any])
def get_team(request):
    """Quién eres y a quiénes se puede traspasar."""
    return episodes.team(request.user)


@router.post("/{patient_id}/pendings/{pending_id}/close", response=dict[str, Any])
def close_pending(request, patient_id: int, pending_id: str):
    try:
        return episodes.close_pending(request.user, patient_id, pending_id)
    except episodes.EpisodeError as error:
        raise HttpError(409, str(error)) from error


@router.post("/{patient_id}/charted", response=dict[str, list[str]])
def mark_charted(request, patient_id: int, payload: ChartIn):
    """Confirma que las atenciones indicadas ya se pegaron en la ficha institucional."""
    try:
        return {"encounterIds": episodes.mark_charted(request.user, patient_id, payload.encounter_ids)}
    except episodes.EpisodeError as error:
        raise HttpError(409, str(error)) from error


@router.post("/{patient_id}/charted/undo", response=dict[str, list[str]])
def unmark_charted(request, patient_id: int, payload: ChartIn):
    """Las atenciones vuelven a quedar por pasar a la ficha."""
    try:
        return {
            "encounterIds": episodes.unmark_charted(request.user, patient_id, payload.encounter_ids)
        }
    except episodes.EpisodeError as error:
        raise HttpError(409, str(error)) from error


@router.get("/handoffs", response=list[dict[str, Any]])
def list_handoffs(request):
    """Traspasos que enviaste o recibiste, del más reciente al más antiguo."""
    return episodes.list_handoffs(request.user)


@router.post("/handoffs", response={201: dict[str, Any]})
def send_handoff(request, payload: HandoffIn):
    try:
        return 201, episodes.send_handoff(
            request.user, payload.to_id, payload.note, payload.snapshots
        )
    except episodes.EpisodeError as error:
        raise HttpError(409, str(error)) from error
