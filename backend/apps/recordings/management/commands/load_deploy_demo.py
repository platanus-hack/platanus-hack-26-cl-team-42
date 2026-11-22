"""Carga los datos de la demo desplegada: Tomás Werth, dos kinesiólogos y tres pacientes.

    manage.py load_deploy_demo [--password CLAVE]

Tomás Werth (médico) deja un informe de María Jesús Navarrete, Clemente Vial y Agustin Reyman, y
los traspasa a Cristóbal Tubino (kinesiólogo). Nelson Salazar (kinesiólogo) queda sin
pacientes. También carga perfiles de agente de miembros de la clínica sin cuenta
(``load_agent_profiles``).
El audio de Cristóbal (``sample_audios/demo``) se sube desde la app: su transcripción y su
registro ya están en la caché, así que no usa el modelo, y al guardarlo se alerta un estudio
negativo sin informar y se abre un conflicto con el informe de Tomás.

Las cuentas son @localhost: la rotación de claves del túnel (``rotate_demo_passwords``) las
cubre. Sin ``--password`` se genera una clave aleatoria que se imprime una sola vez. Es
idempotente: lo ya cargado no se repite.
"""

import logging
import secrets
from contextlib import ExitStack
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings import deploy_demo
from apps.recordings.models import Patient, Recording
from apps.recordings.services import create_recording
from apps.transcription import (
    episode_services,
    evidence_services,
    extraction_services,
    reconciliation_services,
    report_services,
)
from apps.transcription.models import (
    Evidence,
    ExtractedRecord,
    Handoff,
    Report,
    Transcription,
)
from apps.users import shifts


class Command(BaseCommand):
    help = "Carga la demo desplegada: médico, kinesiólogos, tres pacientes y el traspaso."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", help="Clave de las cuentas nuevas (por defecto, aleatoria)."
        )

    def handle(self, *args, password: str | None, **options):
        password = password or secrets.token_urlsafe(12)
        staff, created = self._staff(password)
        for user in staff.values():
            shifts.start_shift(user, hours=12)
        patients = self._patients(staff["tomas"])
        with ExitStack() as stack:
            # Sin modelo de lenguaje ni worker: nada de esto gasta créditos.
            logging.disable(logging.CRITICAL)
            stack.callback(logging.disable, logging.NOTSET)
            stack.enter_context(
                patch.object(extraction_services, "complete_json", side_effect=ValueError("demo"))
            )
            stack.enter_context(
                patch.object(reconciliation_services, "_enqueue_guidance", lambda _id: None)
            )
            self._reports(staff["tomas"], patients)
        self._evidence(staff["tomas"], patients[deploy_demo.CLEMENTE])
        self._handoff(staff["tomas"], staff["cristobal"], patients)
        # Miembros de la clínica sin cuenta que también opinan en el consejo de agentes.
        call_command("load_agent_profiles", stdout=StringIO())
        self._summary(staff, created, password)

    # -- piezas ---------------------------------------------------------------------------

    def _staff(self, password: str) -> tuple[dict, list[str]]:
        users = get_user_model()
        keys = ["tomas", "cristobal", "nelson"]
        staff, created = {}, []
        for key, (email, name, profession) in zip(keys, deploy_demo.STAFF, strict=True):
            user, was_created = users.objects.get_or_create(
                email=email, defaults={"name": name, "profession": profession}
            )
            if was_created:
                user.set_password(password)
                user.save()
                created.append(email)
            staff[key] = user
        return staff, created

    def _patients(self, tomas) -> dict[str, Patient]:
        patients = {}
        for identifier, name, bed in deploy_demo.PATIENTS:
            patient, created = Patient.objects.get_or_create(
                identifier=identifier, defaults={"name": name, "bed": bed}
            )
            if created:  # al recargar, un paciente ya traspasado no vuelve a Tomás
                patient.assigned_to.add(tomas)
            patients[name] = patient
        return patients

    def _reports(self, tomas, patients: dict[str, Patient]) -> None:
        beds = {name: patient.bed for name, patient in patients.items()}
        for name, data in deploy_demo.tomas_reports(beds).items():
            if Report.objects.filter(patient=patients[name]).exists():
                continue
            hours_ago = deploy_demo.TOMAS_HOURS_AGO[name]
            _saved(tomas, patients[name], "medico", hours_ago, data)

    def _evidence(self, tomas, clemente: Patient) -> None:
        if Evidence.objects.filter(patient=clemente).exists():
            return
        for item in deploy_demo.clemente_evidence():
            evidence_services.add_evidence(
                tomas,
                clemente.id,
                kind=item["kind"],
                title=item["title"],
                taken_at=deploy_demo.evidence_time(item["hours_ago"]),
                results=item["results"],
                findings=item["findings"],
            )

    def _handoff(self, tomas, cristobal, patients: dict[str, Patient]) -> None:
        if Handoff.objects.filter(from_user=tomas, to_user=cristobal).exists():
            return
        ids = {str(patient.id) for patient in patients.values()}
        records = episode_services.episode_records(tomas)
        snapshots = [_snapshot(r) for r in records if r["episode"]["id"] in ids]
        episode_services.send_handoff(tomas, cristobal.id, deploy_demo.HANDOFF_NOTE, snapshots)

    def _summary(self, staff: dict, created: list[str], password: str) -> None:
        self.stdout.write(self.style.SUCCESS("Demo desplegada cargada."))
        for user in staff.values():
            note = (
                f"clave {password}" if user.email in created else "ya existía (clave sin cambios)"
            )
            self.stdout.write(f"  {user.email} · {user.name} · {user.profession} · {note}")
        self.stdout.write(
            "Audio de Cristóbal Tubino (súbelo en Clemente Vial):\n"
            f"  {deploy_demo.TUBINO_AUDIO}\n"
            "Si lo copias a otro equipo, deja su fecha de modificación en el día de la demo "
            "(`touch <archivo>`): la alerta compara el informe con los exámenes de ±24 h."
        )


def _snapshot(record: dict) -> dict:
    """Copia fija de lo que se comunica en el traspaso (la misma forma que arma el frontend)."""
    episode = record["episode"]
    encounters = sorted(record["encounters"], key=lambda e: e["occurredAt"])
    entries = [
        {
            "entryId": entry["id"],
            "encounterId": encounter["id"],
            "authorId": encounter["authorId"],
            "occurredAt": encounter["occurredAt"],
            "kind": entry["kind"],
            "text": entry["text"],
        }
        for encounter in encounters
        for entry in encounter["entries"]
    ]
    last = encounters[-1] if encounters else None
    pendings = record["pendings"]
    lines = [
        "TRASPASO DE PACIENTE",
        f"{episode['label']}",
        "",
        "Pendientes:",
        *(f"  {pending['title']}" for pending in pendings),
    ]
    return {
        "episodeId": episode["id"],
        "episodeLabel": episode["label"],
        "cutoffAt": episode["cutoffAt"],
        "summaryText": "\n".join(lines),
        "recentChanges": list(reversed(entries)),
        "plan": [entry for entry in entries if entry["kind"] == "plan"],
        "cutoffData": [],
        "pendings": pendings,
        "openConflicts": record["openConflicts"],
        "lastEncounter": last
        and {
            "encounterId": last["id"],
            "authorId": last["authorId"],
            "occurredAt": last["occurredAt"],
        },
    }


def _saved(author, patient: Patient, profession: str, hours_ago: float, data: dict) -> Report:
    """Informe validado y guardado: se consolida (o abre una reconciliación) como en la app."""
    report = _draft(author, patient, profession, hours_ago, data)
    for point in report_services.pending_review_items(report):
        report_services.review_item(report, point.id)
    return report_services.validate_report(report)


def _draft(author, patient: Patient, profession: str, hours_ago: float, data: dict) -> Report:
    """Informe homologado a la espera de que su autor lo valide (sin audio real)."""
    recording = create_recording(
        professional=author,
        audio=SimpleUploadedFile("demo.wav", b"RIFFdemo", "audio/wav"),
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now() - timedelta(hours=hours_ago),
        patient=patient,
        profession=profession,
    )
    transcription = Transcription.objects.create(
        recording=recording,
        status=Transcription.Status.DONE,
        text=data.get("resumen_24h") or "Dictado de demostración.",
        language="spanish",
        model_id="demo",
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(profession),
        status=ExtractedRecord.Status.DONE,
        data=data,
    )
    return report_services.generate_report(record)
