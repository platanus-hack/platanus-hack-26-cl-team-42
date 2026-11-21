"""Arma un escenario de demo completo: varios profesionales, cada uno con sus pacientes y casos.

    manage.py load_demo_scenario [email]        # por defecto test@localhost (ve a todos)

Crea 9 pacientes ficticios con historias distintas para recorrer toda la app: un paciente crítico
con varias versiones oficiales, uno estable con visita atrasada, un informe por validar, un
dictado que falló y otro que se procesa, un conflicto en consenso entre dos profesionales de
turno, uno resuelto con su historial, uno con el otro profesional fuera de turno y una alergia
que contradice una indicación (con el caso anonimizado enviado a un externo).

Los informes pasan por los servicios reales (homologación, validación, consolidación y
reconciliación), sin modelo de lenguaje: no gasta créditos. Es idempotente: un paciente que ya
tiene informes no se vuelve a cargar.
"""

import logging
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.recordings.services import create_recording, delete_recording
from apps.transcription import (
    evidence_services,
    extraction_services,
    reconciliation_services,
    report_services,
)
from apps.transcription.models import (
    Evidence,
    ExtractedRecord,
    Reconciliation,
    Report,
    Transcription,
)
from apps.users import shifts

PASSWORD = "test"
# (correo, nombre, profesión): se crean si no existen. EU Díaz termina su turno al final.
STAFF = [
    ("medico@localhost", "Dr. Rojas", "medico"),
    ("medico2@localhost", "Dra. Vega", "medico"),
    ("enfermeria@localhost", "EU Soto", "enfermeria"),
    ("enfermeria2@localhost", "EU Díaz", "enfermeria"),
    ("kinesiologia@localhost", "Klgo. Muñoz", "kinesiologia"),
    ("nutricionista@localhost", "Nut. Parra", "nutricionista"),
    ("especialista@localhost", "Dra. Fuentes", "especialista"),
]
OFF_SHIFT = "enfermeria2@localhost"
# Quién tiene a quién (además de la cuenta que ve todo). La externa no tiene pacientes.
PATIENTS = [
    (
        "21.001.001-1",
        "Marta Silva Pino",
        "Box 4",
        ["medico", "enfermeria", "kinesiologia", "nutricionista"],
    ),
    ("21.002.002-2", "Pedro Núñez Lara", "Box 6", ["medico", "enfermeria"]),
    ("21.003.003-3", "Elena Ruiz Cortés", "Box 8", ["medico2", "enfermeria2"]),
    ("21.004.004-4", "Hugo Salinas Mora", "Box 10", ["medico2", "nutricionista"]),
    ("21.005.005-5", "Camila Rojas Vera", "Box 11", ["medico2", "enfermeria2"]),
    ("21.006.006-6", "Tomás Araya Peña", "Box 12", ["medico2", "enfermeria2"]),
    ("21.007.007-7", "Lucía Vargas Díaz", "Box 13", ["kinesiologia", "enfermeria"]),
    ("21.008.008-8", "Diego Fuentes Mora", "Box 14", ["medico", "kinesiologia", "nutricionista"]),
    ("21.009.009-9", "Sofía Lagos Vidal", "Box 15", ["medico", "medico2"]),
]


# Los pacientes de ``load_demo_patients`` (salvo Juan Pérez, de la historia de conflictos) se
# reparten entre profesionales: cada uno ve solo a los suyos.
LEGACY_PATIENTS = {
    "12.222.222-2": ["medico", "enfermeria"],
    "13.333.333-3": ["medico", "kinesiologia"],
    "14.444.444-4": ["medico2", "enfermeria2"],
    "15.555.555-5": ["medico2"],
    "16.666.666-6": ["medico2", "kinesiologia"],
}


class Command(BaseCommand):
    help = "Carga un escenario de demo con varios profesionales, pacientes y casos."

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?", default="test@localhost")

    def handle(self, *args, email: str, **options):
        admin = get_user_model().objects.filter(email=email).first()
        if admin is None:
            raise CommandError(f"No existe la cuenta {email}.")
        with ExitStack() as stack:
            # Sin modelo de lenguaje, la homologación y la revisión de evidencia registran un error
            # esperado en cada informe; aquí es ruido, así que no se muestra.
            logging.disable(logging.CRITICAL)
            stack.callback(logging.disable, logging.NOTSET)
            # Sin modelo de lenguaje ni worker: nada de esto gasta créditos.
            stack.enter_context(
                patch.object(extraction_services, "complete_json", side_effect=ValueError("demo"))
            )
            stack.enter_context(
                patch.object(reconciliation_services, "_enqueue_guidance", lambda _id: None)
            )
            staff = self._staff()
            # Todos de turno mientras se arman las historias (dejan notas y deciden)...
            for user in [admin, *staff.values()]:
                shifts.start_shift(user, hours=12)
            patients = self._patients(admin, staff)
            self._stories(patients, staff)
            self._evidence(patients, staff)
            self._serial_labs(patients, staff)
            # ...y EU Díaz termina su turno al final: así hay un conflicto con alguien ausente.
            self._turns(staff)
        self.stdout.write(self.style.SUCCESS("Escenario de demo cargado."))
        for account in staff.values():
            self.stdout.write(f"  {account.email} (clave {PASSWORD}) · {account.name}")

    # -- personas -------------------------------------------------------------------------

    def _staff(self) -> dict[str, object]:
        users = get_user_model()
        staff = {}
        for account_email, name, profession in STAFF:
            user, created = users.objects.get_or_create(
                email=account_email, defaults={"name": name, "profession": profession}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            staff[account_email.split("@")[0]] = user
        return staff

    def _patients(self, admin, staff) -> dict[str, Patient]:
        patients = {}
        for identifier, name, bed, owners in PATIENTS:
            patient, _ = Patient.objects.get_or_create(
                identifier=identifier, defaults={"name": name, "bed": bed}
            )
            patient.assigned_to.add(admin, *(staff[owner] for owner in owners))
            patients[name.split()[0]] = patient
        for identifier, owners in LEGACY_PATIENTS.items():
            legacy = Patient.objects.filter(identifier=identifier).first()
            if legacy is None:
                continue
            legacy.assigned_to.remove(*staff.values())
            legacy.assigned_to.add(admin, *(staff[owner] for owner in owners))
        return patients

    def _turns(self, staff) -> None:
        shifts.end_shift(staff[OFF_SHIFT.split("@")[0]])
        # Con EU Díaz ya fuera de turno, los conflictos conceptuales envían el caso anonimizado.
        for reconciliation in Reconciliation.objects.filter(status=Reconciliation.Status.OPEN):
            reconciliation_services.send_anonymized_if_needed(reconciliation)

    # -- historias ------------------------------------------------------------------------

    def _stories(self, patients, staff) -> None:
        for story in (
            self._marta,
            self._pedro,
            self._elena,
            self._hugo,
            self._camila,
            self._tomas,
            self._lucia,
            self._diego,
            self._diego_requests,
            self._diego_kinesiology,
            self._area_records,
            self._nutrition_records,
        ):
            story(patients, staff)

    def _marta(self, patients, staff) -> None:
        """Crítica: tres informes que se suman sin conflictos (versión oficial n.º 2 al final)."""
        patient = patients["Marta"]
        if self._done(patient):
            return
        self._saved(
            staff["medico"],
            patient,
            "medico",
            hours_ago=9,
            data=medico(
                "Box 4",
                4,
                dx=("Shock séptico de foco pulmonar", "J15.9"),
                let="Sin limitación del esfuerzo terapéutico; manejo completo.",
                summary="Neumonía grave en VMI con shock séptico: noradrenalina en alza, SOFA 12.",
                resp="VMI",
                sat=92,
                drugs=[drug("norepinefrina", 0.25, "aumento")],
                meds=[med("meropenem", 1, "g", "EV", "cada 8 h")],
                devices=[device("CVC", "yugular derecha"), device("TET", "orotraqueal")],
                scales=[
                    scale("SOFA", 12, "disfunción multiorgánica severa"),
                    scale("APACHE II", 27, "mortalidad predicha cercana al 55 %"),
                ],
                alerts=[alert("Hipoxemia refractaria con PaFi 120", "alta")],
                pending=[
                    task("Control de gases arteriales", "en 2 h"),
                    task("Evaluar prono", "hoy"),
                ],
                indications=[
                    task("Mantener PAM >= 65 titulando noradrenalina", "durante el turno")
                ],
                goals=[goal("Saturación", ">= 92 %")],
            ),
        )
        self._saved(
            staff["kinesiologia"],
            patient,
            "kinesiologia",
            hours_ago=3,
            data={
                "metadatos": meta("kinesiologia", "Klgo. Muñoz", "Box 4", 4),
                "control_respiratorio": [resp_item("VMI", 91)],
                "escalas": [scale("RASS", -3, "sedación profunda")],
                "objetivos_terapeuticos": [{"objetivo": "Optimizar secreciones", "plazo": "hoy"}],
                "recomendaciones_equipo": [
                    task("Evaluar posición prono con el equipo médico", "hoy")
                ],
            },
        )

    def _pedro(self, patients, staff) -> None:
        """Moderado: dos conflictos de valor entre dos profesionales de turno (para el consenso)."""
        patient = patients["Pedro"]
        if self._done(patient):
            return
        self._saved(
            staff["medico"],
            patient,
            "medico",
            hours_ago=6,
            data=medico(
                "Box 6",
                2,
                dx=("Insuficiencia respiratoria por EPOC reagudizado", "J44.1"),
                let="LET acordada con la familia: no intubar y no RCP; soporte no invasivo.",
                summary="EPOC reagudizado en alto flujo, mejorando; evaluar descenso de soporte.",
                resp="Cánula nasal de alto flujo",
                sat=94,
                meds=[med("enoxaparina", 40, "mg", "SC", "cada 24 h")],
                devices=[device("CVC", "yugular derecha")],
                alerts=[alert("Retención de CO2 en el último gas", "media")],
                pending=[task("Control de gases en la tarde", "16:00")],
                indications=[task("Corticoides endovenosos por 5 días", "5 días")],
            ),
        )
        report = self._saved(
            staff["enfermeria"],
            patient,
            "enfermeria",
            hours_ago=0.4,
            data={
                "metadatos": meta("enfermeria", "EU Soto", "Box 6", 2),
                "medicamentos": [med("enoxaparina", 60, "mg", "SC", "cada 24 h")],
                "dispositivos_invasivos": [device("CVC", "femoral derecha")],
                "control_respiratorio": [resp_item("Cánula nasal de alto flujo", 95)],
            },
        )
        for conflict in report.reconciliations.get().conflicts.all():
            if conflict.section == "medicamentos":
                reconciliation_services.add_note(
                    conflict,
                    staff["enfermeria"],
                    "La indicación de la ficha dice 60 mg por peso; así se administró a las 08:00.",
                )
                reconciliation_services.add_note(
                    conflict,
                    staff["medico"],
                    "Mi dictado fue con 40 mg: el peso del ingreso era de 62 kg. Reviso la ficha.",
                )
                reconciliation_services.propose(conflict, staff["enfermeria"], "b", None)
            else:
                reconciliation_services.add_note(
                    conflict,
                    staff["enfermeria"],
                    "Al cambiar el apósito vi el catéter en la ingle, no en el cuello.",
                )

    def _elena(self, patients, staff) -> None:
        """Estable, con visita atrasada y un conflicto con la enfermera, ya fuera de turno."""
        patient = patients["Elena"]
        if self._done(patient):
            return
        self._saved(
            staff["medico2"],
            patient,
            "medico",
            hours_ago=15,
            data=medico(
                "Box 8",
                1,
                dx=("Posoperatorio de colecistectomía", "K80.2"),
                summary="Posoperatorio estable, afebril, con analgesia oral; vigilar glicemias.",
                resp="Cánula nasal",
                sat=97,
                meds=[med("insulina cristalina", 6, "UI", "SC", "según esquema")],
                devices=[device("Vía venosa periférica", "antebrazo izquierdo")],
                pending=[task("Control de glicemia en ayunas", "mañana 06:00")],
            ),
        )
        self._saved(
            staff["enfermeria2"],
            patient,
            "enfermeria",
            hours_ago=14,
            data={
                "metadatos": meta("enfermeria", "EU Díaz", "Box 8", 1),
                "medicamentos": [med("insulina cristalina", 10, "UI", "SC", "según esquema")],
                "control_respiratorio": [resp_item("Cánula nasal", 97)],
            },
        )

    def _hugo(self, patients, staff) -> None:
        """Informe propio por validar (la bandeja de la doctora lo marca como pendiente)."""
        patient = patients["Hugo"]
        # Una versión anterior de la demo no traía exámenes en el informe: se arma de nuevo.
        previous = Report.objects.filter(patient=patient).first()
        if previous and "examenes" not in (previous.data or {}):
            for recording in Recording.objects.filter(patient=patient):
                delete_recording(recording)
        if self._done(patient):
            return
        self._draft(
            staff["medico2"],
            patient,
            "medico",
            hours_ago=1,
            data=medico(
                "Box 10",
                3,
                dx=("Pancreatitis aguda grave", "K85.9"),
                summary="Pancreatitis biliar con dolor controlado, en ayuno e hidratación.",
                resp="Cánula nasal",
                sat=96,
                meds=[med("paracetamol", 1, "g", "EV", "cada 8 h")],
                alerts=[alert("Lipasa elevada, tendencia a la baja", "media")],
                pending=[
                    task("Ecografía abdominal", "hoy"),
                    task("Reevaluar inicio de dieta", "mañana"),
                ],
                # Lo que dice el informe frente a los exámenes de hoy (ver ``_evidence``): la
                # lipasa y la creatinina no coinciden y el potasio no se menciona.
                exams=[
                    exam("Lipasa", 320, "U/L", "en descenso"),
                    exam("Creatinina", 0.9, "mg/dL", "normal"),
                ],
            ),
        )

    def _camila(self, patients, staff) -> None:
        """Alto: un conflicto ya resuelto, con sus notas y una versión por reconciliación."""
        patient = patients["Camila"]
        if self._done(patient):
            return
        self._saved(
            staff["medico2"],
            patient,
            "medico",
            hours_ago=10,
            data=medico(
                "Box 11",
                5,
                dx=("Estado epiléptico refractario", "G41.9"),
                summary="Crisis refractarias controladas con midazolam en infusión, con EEG.",
                resp="VMI",
                sat=98,
                drugs=[drug("midazolam", 2, "sin_cambio", "mg/h")],
                devices=[device("TET", "orotraqueal")],
                alerts=[alert("Riesgo de nueva crisis al bajar sedación", "media")],
                pending=[task("EEG continuo", "24 h")],
            ),
        )
        report = self._saved(
            staff["enfermeria2"],
            patient,
            "enfermeria",
            hours_ago=6,
            data={
                "metadatos": meta("enfermeria", "EU Díaz", "Box 11", 5),
                "drogas_infusion": [drug("midazolam", 4, "sin_cambio", "mg/h")],
            },
        )
        conflict = report.reconciliations.get().conflicts.get()
        reconciliation_services.add_note(
            conflict,
            staff["enfermeria2"],
            "La bomba marcaba 4 mg/h desde las 02:00, tras la crisis de la madrugada.",
        )
        reconciliation_services.add_note(
            conflict,
            staff["medico2"],
            "Tiene razón: subí la dosis esa noche y no actualicé mi dictado.",
        )
        reconciliation_services.accept_other(conflict, staff["medico2"])

    def _tomas(self, patients, staff) -> None:
        """Alergia contra una indicación; sin la enfermera de turno, el caso va a un externo."""
        patient = patients["Tomás"]
        if self._done(patient):
            return
        self._saved(
            staff["medico2"],
            patient,
            "medico",
            hours_ago=7,
            data=medico(
                "Box 12",
                2,
                dx=("Neumonía adquirida en la comunidad", "J18.9"),
                summary="Neumonía lobar derecha con requerimiento de oxígeno, hemodinamia estable.",
                resp="Cánula nasal de alto flujo",
                sat=93,
                meds=[med("amoxicilina", 1, "g", "EV", "cada 8 h")],
                scales=[scale("SOFA", 7, "disfunción moderada")],
                alerts=[alert("Requerimiento creciente de oxígeno", "media")],
                pending=[task("Radiografía de control", "mañana")],
            ),
        )
        self._saved(
            staff["enfermeria2"],
            patient,
            "enfermeria",
            hours_ago=5,
            data={
                "metadatos": meta("enfermeria", "EU Díaz", "Box 12", 2),
                "alergias": [
                    {
                        "agente": "penicilina",
                        "reaccion": "rash cutáneo",
                        "evidencia": "el paciente cuenta que de niño le dio rash con penicilina",
                    }
                ],
            },
        )

    def _lucia(self, patients, staff) -> None:
        """Informe guardado de kinesiología (reemplaza el dictado fallido de versiones previas)."""
        patient = patients["Lucía"]
        failed = Recording.objects.filter(
            patient=patient, transcription__status=Transcription.Status.FAILED
        )
        for recording in failed:
            delete_recording(recording)
        if self._done(patient):
            return
        self._saved(
            staff["kinesiologia"],
            patient,
            "kinesiologia",
            hours_ago=5,
            data={
                "metadatos": meta("kinesiologia", "Klgo. Muñoz", "Box 13", 3),
                "control_respiratorio": [resp_item("Cánula nasal de alto flujo", 95)],
                "escalas": [scale("RASS", 0, "alerta y tranquila")],
                "objetivos_terapeuticos": [
                    {
                        "objetivo": "Destete de oxígeno: bajar el flujo si la saturación se "
                        "mantiene sobre 94 %",
                        "plazo": "24 horas",
                    },
                    {"objetivo": "Sedestación y marcha asistida", "plazo": "hoy"},
                ],
                "recomendaciones_equipo": [task("Control de gases antes de bajar el flujo", "hoy")],
            },
        )

    def _diego(self, patients, staff) -> None:
        """Informe guardado de un paciente de riesgo alto (en VMI con sedación)."""
        patient = patients["Diego"]
        self._remove_unfinished(patient)
        if self._done(patient):
            return
        self._saved(
            staff["medico"],
            patient,
            "medico",
            hours_ago=2,
            data=medico(
                "Box 14",
                6,
                dx=("Traumatismo craneoencefálico grave", "S06.9"),
                summary="TCE grave en VMI y sedación, con presión intracraneana controlada.",
                resp="VMI",
                sat=97,
                drugs=[drug("propofol", 1.5, "sin_cambio", "mg/kg/h")],
                devices=[device("TET", "orotraqueal")],
                alerts=[alert("Hipertensión endocraneana controlada con osmoterapia", "media")],
                pending=[task("TAC de cerebro de control", "mañana 08:00")],
                indications=[task("Cabecera a 30 grados y normotermia", "durante el turno")],
            ),
        )

    def _diego_requests(self, patients, staff) -> None:
        """Segundo informe médico de Diego: pide una tarea a kinesiología y otra a enfermería."""
        patient = patients["Diego"]
        doctor = staff["medico"]
        if Report.objects.filter(patient=patient, author=doctor).count() >= 2:
            return
        self._saved(
            doctor,
            patient,
            "medico",
            hours_ago=0.5,
            data=medico(
                "Box 14",
                6,
                dx=("Traumatismo craneoencefálico grave", "S06.9"),
                summary="TCE grave en VMI. Se solicitan tareas a kinesiología y a enfermería.",
                resp="VMI",
                sat=97,
                scales=[scale("SOFA", 8, "disfunción orgánica moderada"), scale("Glasgow", 6, "")],
                pending=[
                    task(
                        "Kinesiología: iniciar kinesiterapia respiratoria y movilización pasiva "
                        "con control de PIC",
                        "hoy 16:00",
                    ),
                    task(
                        "Enfermería: control de pupilas y escala de Glasgow cada 2 horas",
                        "durante el turno",
                    ),
                ],
            ),
        )

    def _diego_kinesiology(self, patients, staff) -> None:
        """Informe de kinesiología de Diego: cumple lo pedido y deja el plan ventilatorio."""
        patient = patients["Diego"]
        kine = staff["kinesiologia"]
        if Report.objects.filter(patient=patient, author=kine).exists():
            return
        self._saved(
            kine,
            patient,
            "kinesiologia",
            hours_ago=0.2,
            data={
                "metadatos": meta("kinesiologia", "Klgo. Muñoz", "Box 14", 6),
                "control_respiratorio": [resp_item("VMI", 97)],
                "escalas": [scale("RASS", -4, "sedación profunda")],
                "objetivos_terapeuticos": [
                    {
                        "objetivo": "Kinesiterapia respiratoria y movilización pasiva realizadas "
                        "según lo indicado, con PIC estable",
                        "plazo": "hoy",
                    },
                    {
                        "objetivo": "Plan ventilatorio: mantener VMI en modo asistido-controlado "
                        "hoy; pasar a presión soporte cuando RASS sea >= -2",
                        "plazo": "48 horas",
                    },
                    {
                        "objetivo": "Progreso: prueba de ventilación espontánea con tubo en T "
                        "si cumple criterios, luego evaluar extubación",
                        "plazo": "72 horas",
                    },
                ],
                "recomendaciones_equipo": [
                    task("Reducir sedación para evaluar despertar diario", "mañana 08:00")
                ],
            },
        )

    def _serial_labs(self, patients, staff) -> None:
        """Controles anteriores de laboratorio, para que se vea la tendencia; idempotente."""
        plan = [
            (
                patients["Marta"],
                staff["medico"],
                [
                    (30.0, [("Lactato", "6.4"), ("Creatinina", "1.1")]),
                    (16.0, [("Lactato", "5.6"), ("Creatinina", "1.6")]),
                    (4.0, [("Lactato", "5.1"), ("Creatinina", "2.1")]),
                ],
            ),
            (
                patients["Hugo"],
                staff["medico2"],
                [
                    (20.0, [("Potasio", "5.4"), ("Creatinina", "1.6")]),
                    (8.0, [("Potasio", "6.2"), ("Creatinina", "2.0")]),
                ],
            ),
            (
                patients["Pedro"],
                staff["medico"],
                [
                    (20.0, [("pCO2", "52")]),
                    (8.0, [("pCO2", "58")]),
                ],
            ),
        ]
        for patient, author, controls in plan:
            if Evidence.objects.filter(patient=patient, title="Control previo").exists():
                continue
            for hours_ago, results in controls:
                evidence_services.add_evidence(
                    author,
                    patient.id,
                    kind="lab",
                    title="Control previo",
                    taken_at=timezone.now() - timedelta(hours=hours_ago),
                    results=[{"name": name, "value": value} for name, value in results],
                    findings="",
                )

    # -- áreas y nutrición ----------------------------------------------------------------

    def _recorded(self, patient: Patient, marker: str) -> bool:
        return ExtractedRecord.objects.filter(
            transcription__recording__patient=patient, data__resumen_24h=marker
        ).exists()

    def _area_records(self, patients, staff) -> None:
        """Informes médicos con las áreas que faltaban: infeccioso, renal, neurológico, balance."""
        marker = "Control por sistemas del turno."
        plan = [
            (
                "Marta",
                "medico",
                ("Shock séptico de foco pulmonar", "J15.9"),
                ("VMI", 92),
                {
                    "antimicrobianos": [
                        {
                            "farmaco": "meropenem",
                            "dosis": "1 g cada 8 h",
                            "dia_tratamiento": 3,
                            "indicacion": "neumonía grave con shock séptico",
                            "accion": "continua",
                            "evidencia": "meropenem día tres",
                        }
                    ],
                    "cultivos": [
                        {
                            "muestra": "hemocultivos x2",
                            "fecha_toma": "ayer",
                            "estado": "pendiente",
                            "microorganismo": None,
                            "sensibilidad": None,
                            "evidencia": "hemocultivos pendientes",
                        }
                    ],
                    "balance_hidrico": {
                        "periodo_horas": 24,
                        "diuresis_ml": 900,
                        "balance_ml": 1800,
                        "balance_acumulado_ml": 4200,
                        "evidencia": "balance positivo de 1800",
                    },
                    "sedoanalgesia_neuro": {"rass_actual": -3, "rass_objetivo": -2, "glasgow": 8},
                },
            ),
            (
                "Hugo",
                "medico2",
                ("Pancreatitis aguda grave", "K85.9"),
                ("Cánula nasal", 96),
                {
                    "balance_hidrico": {
                        "periodo_horas": 24,
                        "diuresis_ml": 600,
                        "balance_ml": 2200,
                        "balance_acumulado_ml": 3100,
                        "evidencia": "balance positivo de 2200, oligúrico",
                    },
                    "terapia_reemplazo_renal": {
                        "modalidad": "CVVH",
                        "dosis_efluente_ml_kg_h": 25,
                        "anticoagulacion": "citrato",
                        "ultrafiltracion_ml": 100,
                        "evidencia": "se inicia CVVH por hiperkalemia y oliguria",
                    },
                    "antimicrobianos": [
                        {
                            "farmaco": "imipenem",
                            "dosis": "500 mg cada 6 h",
                            "dia_tratamiento": 1,
                            "indicacion": "necrosis pancreática infectada",
                            "accion": "inicio",
                            "evidencia": "se inicia imipenem",
                        }
                    ],
                },
            ),
            (
                "Diego",
                "medico",
                ("Traumatismo craneoencefálico grave", "S06.9"),
                ("VMI", 97),
                {
                    "sedoanalgesia_neuro": {
                        "rass_actual": -4,
                        "rass_objetivo": -4,
                        "glasgow": 6,
                        "pupilas": "isocóricas reactivas",
                        "focalidad": "sin focalidad evidente",
                    },
                    "balance_hidrico": {
                        "periodo_horas": 24,
                        "diuresis_ml": 1700,
                        "balance_ml": -300,
                        "balance_acumulado_ml": 400,
                        "evidencia": "balance levemente negativo con osmoterapia",
                    },
                },
            ),
        ]
        for name, who, dx, (resp, sat), extra in plan:
            patient = patients[name]
            if self._recorded(patient, marker):
                continue
            self._saved(
                staff[who],
                patient,
                "medico",
                hours_ago=1.2,
                data=medico(patient.bed, 6, dx=dx, summary=marker, resp=resp, sat=sat, extra=extra),
            )

    def _nutrition_records(self, patients, staff) -> None:
        """Informes de nutrición: estado nutricional, requerimientos, soporte y recomendaciones."""
        nutritionist = staff["nutricionista"]
        plan = [
            (
                "Marta",
                {
                    "valoracion_nutricional": _nutrition_status(
                        "riesgo de desnutrición", 72, 165, 26.4, "NUTRIC alto"
                    ),
                    "requerimientos": _requirements(1800, 1.5),
                    "nutricion": _feeding("SNG", "polimérica hiperproteica", 40, 1800, 900, 60),
                    "recomendaciones_equipo": [
                        _advice("Avanzar nutrición enteral hasta alcanzar la meta calórica", "48 h")
                    ],
                },
            ),
            (
                "Hugo",
                {
                    "valoracion_nutricional": _nutrition_status(
                        "desnutrición moderada", 64, 172, 21.6, "NUTRIC alto"
                    ),
                    "requerimientos": _requirements(1900, 1.8),
                    "nutricion": _feeding(
                        "parenteral", "nutrición parenteral total", 60, 1900, 1500, None
                    ),
                    "recomendaciones_equipo": [
                        _advice("Reevaluar vía enteral distal al píloro si baja el dolor", "72 h"),
                        _advice(
                            "Controlar triglicéridos y glicemia con la nutrición parenteral",
                            "diario",
                        ),
                    ],
                },
            ),
            (
                "Diego",
                {
                    "valoracion_nutricional": _nutrition_status(
                        "eutrófico", 80, 178, 25.2, "NUTRIC bajo"
                    ),
                    "requerimientos": _requirements(2200, 1.5),
                    "nutricion": _feeding("SNG", "polimérica estándar", 70, 2200, 1500, 20),
                    "recomendaciones_equipo": [
                        _advice("Mantener cabecera a 30° durante la infusión enteral", "continuo")
                    ],
                },
            ),
        ]
        for name, extra in plan:
            patient = patients[name]
            if Report.objects.filter(patient=patient, author=nutritionist).exists():
                continue
            data = {
                "metadatos": meta("nutricionista", "Nut. Parra", patient.bed, 4),
                "resumen_24h": None,
                **extra,
            }
            self._saved(nutritionist, patient, "nutricionista", hours_ago=0.9, data=data)

    def _evidence(self, patients, staff) -> None:
        """Exámenes de los pacientes (además de los dictados); idempotente por paciente."""
        juan = Patient.objects.filter(identifier="11.111.111-1").first()
        plan = [
            (
                patients["Hugo"],
                staff["medico2"],
                [
                    (
                        "lab",
                        "Química y enzimas",
                        1.0,
                        [("Lipasa", "1450"), ("Creatinina", "2.4"), ("Potasio", "6.9")],
                        "",
                    ),
                ],
            ),
            (
                patients["Marta"],
                staff["medico"],
                [
                    (
                        "lab",
                        "Gases arteriales y lactato",
                        2.0,
                        [("Lactato", "4.8"), ("pH", "7.28"), ("PCR", "210")],
                        "",
                    ),
                    (
                        "imaging",
                        "Radiografía de tórax",
                        5.0,
                        [],
                        "Infiltrados alveolares bilaterales; tubo bien posicionado.",
                    ),
                ],
            ),
            (
                patients["Pedro"],
                staff["medico"],
                [
                    (
                        "lab",
                        "Gasometría arterial",
                        1.5,
                        [("pH", "7.31"), ("pCO2", "62"), ("pO2", "74")],
                        "",
                    ),
                ],
            ),
            (
                patients["Elena"],
                staff["medico2"],
                [
                    (
                        "lab",
                        "Glicemia capilar y química",
                        3.0,
                        [("Glicemia", "280"), ("Creatinina", "0.8")],
                        "",
                    ),
                ],
            ),
            (
                patients["Tomás"],
                staff["medico2"],
                [
                    ("lab", "Hemograma y PCR", 4.0, [("Leucocitos", "16.5"), ("PCR", "140")], ""),
                    (
                        "culture",
                        "Cultivo de expectoración",
                        6.0,
                        [],
                        "Streptococcus pneumoniae, sensible a penicilina y ceftriaxona.",
                    ),
                ],
            ),
            (
                patients["Camila"],
                staff["medico2"],
                [
                    ("lab", "Química", 8.0, [("Creatinina", "0.8"), ("Sodio", "139")], ""),
                ],
            ),
            (
                patients["Diego"],
                staff["medico"],
                [
                    (
                        "imaging",
                        "TAC de cerebro",
                        3.0,
                        [],
                        "Contusiones frontales bilaterales sin desplazamiento de línea media.",
                    ),
                ],
            ),
        ]
        if juan is not None:
            plan.append(
                (
                    juan,
                    staff["medico"],
                    [
                        ("lab", "Química", 2.0, [("Creatinina", "1.1"), ("PCR", "180")], ""),
                        (
                            "culture",
                            "Hemocultivo",
                            5.0,
                            [],
                            "Streptococcus pneumoniae, sensible a penicilina.",
                        ),
                    ],
                )
            )
        for patient, author, items in plan:
            if Evidence.objects.filter(patient=patient).exists():
                continue
            for kind, title, hours_ago, results, findings in items:
                evidence_services.add_evidence(
                    author,
                    patient.id,
                    kind=kind,
                    title=title,
                    taken_at=timezone.now() - timedelta(hours=hours_ago),
                    results=[{"name": name, "value": value} for name, value in results],
                    findings=findings,
                )

    # -- piezas ---------------------------------------------------------------------------

    @staticmethod
    def _remove_unfinished(patient: Patient) -> None:
        """Borra dictados de demo que quedaron «procesando»: sin tarea real, nunca terminarían."""
        stuck = Recording.objects.filter(
            patient=patient,
            transcription__status__in=[
                Transcription.Status.PENDING,
                Transcription.Status.PROCESSING,
            ],
        )
        for recording in stuck:
            delete_recording(recording)

    @staticmethod
    def _done(patient: Patient) -> bool:
        """Un paciente que ya tiene informes se considera cargado."""
        return Report.objects.filter(patient=patient).exists()

    def _recording(self, author, patient, profession, hours_ago: float) -> Recording:
        return create_recording(
            professional=author,
            audio=SimpleUploadedFile("demo.wav", b"RIFFdemo", "audio/wav"),
            source=Recording.Source.UPLOAD,
            recorded_at=timezone.now() - timedelta(hours=hours_ago),
            patient=patient,
            profession=profession,
        )

    def _draft(self, author, patient, profession, hours_ago: float, data: dict) -> Report:
        """Informe homologado a la espera de que su autor lo valide."""
        recording = self._recording(author, patient, profession, hours_ago)
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

    def _saved(self, author, patient, profession, hours_ago: float, data: dict) -> Report:
        """Informe validado y guardado: se consolida (o abre una reconciliación) como en la app."""
        report = self._draft(author, patient, profession, hours_ago, data)
        report.validated_sections = [t.id for t in report_services.topics_of(report)]
        report.save()
        return report_services.validate_report(report)


# --- constructores de datos de dictado ---------------------------------------------------


def meta(profession: str, name: str, bed: str, day: int) -> dict:
    return {
        "tipo_profesional": profession,
        "nombre_profesional": name,
        "cama": bed,
        "dia_estada_uci": day,
    }


def drug(name: str, dose: float, trend: str = "sin_cambio", unit: str = "mcg/kg/min") -> dict:
    return {
        "farmaco": name,
        "categoria": "vasoactivo" if name in ("norepinefrina", "noradrenalina") else "sedante",
        "dosis": dose,
        "unidad": unit,
        "tendencia": trend,
        "evidencia": f"{name} a {dose} {unit}",
    }


def med(name: str, dose: float, unit: str, route: str, frequency: str) -> dict:
    return {
        "nombre": name,
        "dosis": dose,
        "unidad": unit,
        "via": route,
        "frecuencia": frequency,
        "evidencia": f"{name} {dose} {unit} {route} {frequency}",
    }


def device(kind: str, place: str) -> dict:
    return {"tipo": kind, "ubicacion": place, "evidencia": f"{kind} en {place}"}


def scale(name: str, score: int, reading: str) -> dict:
    return {
        "nombre": name,
        "puntaje": score,
        "interpretacion": reading,
        "evidencia": f"{name} de {score}",
    }


def alert(description: str, severity: str) -> dict:
    return {"descripcion": description, "severidad": severity, "evidencia": description}


def task(description: str, deadline: str) -> dict:
    return {"descripcion": description, "plazo": deadline, "evidencia": description}


def exam(name: str, value: float, unit: str, reading: str) -> dict:
    return {
        "examen": name,
        "valor": value,
        "unidad": unit,
        "interpretacion": reading,
        "evidencia": f"{name} {value} {unit}",
    }


def goal(parameter: str, target: str) -> dict:
    return {"parametro": parameter, "objetivo": target, "evidencia": f"{parameter} {target}"}


def resp_item(support: str, saturation: int) -> dict:
    return {
        "soporte": support,
        "saturacion_o2": saturation,
        "evidencia": f"{support}, sat {saturation}",
    }


def medico(
    bed: str,
    day: int,
    *,
    dx: tuple[str, str],
    summary: str,
    resp: str,
    sat: int,
    drugs: list | None = None,
    meds: list | None = None,
    devices: list | None = None,
    scales: list | None = None,
    alerts: list | None = None,
    pending: list | None = None,
    indications: list | None = None,
    goals: list | None = None,
    exams: list | None = None,
    extra: dict | None = None,
    let: str = "",
) -> dict:
    """Dictado de un médico de UCI con las secciones que usa la demo."""
    data = {
        "metadatos": meta("medico", "", bed, day),
        "ingreso": {"limitacion_esfuerzo_terapeutico": let} if let else {},
        "resumen_24h": summary,
        "diagnosticos": [
            {
                "descripcion": dx[0],
                "codigo_cie10": dx[1],
                "estado": "confirmado",
                "evidencia": f"diagnóstico {dx[0].lower()}",
            }
        ],
        "control_respiratorio": [resp_item(resp, sat)],
        "drogas_infusion": drugs or [],
        "medicamentos": meds or [],
        "dispositivos_invasivos": devices or [],
        "escalas": scales or [],
        "alergias": [],
        "alertas": alerts or [],
        "pendientes": pending or [],
        "indicaciones": indications or [],
        "metas_del_dia": goals or [],
        "examenes": exams or [],
    }
    data.update(extra or {})
    return data


def _nutrition_status(state: str, weight: float, height: float, bmi: float, risk: str) -> dict:
    return {
        "estado_nutricional": state,
        "peso_kg": weight,
        "talla_cm": height,
        "imc": bmi,
        "riesgo_nutricional": risk,
        "evidencia": f"{state}, {risk}",
    }


def _requirements(kcal: int, protein: float) -> dict:
    return {
        "kcal_dia": kcal,
        "proteinas_g_kg": protein,
        "evidencia": f"meta {kcal} kcal y {protein} g/kg de proteína",
    }


def _feeding(via, formula, rate, goal, intake, residual) -> dict:
    return {
        "via": via,
        "formula": formula,
        "velocidad_ml_h": rate,
        "meta_kcal": goal,
        "aporte_kcal": intake,
        "tolerancia": "buena" if residual is not None else "sin complicaciones",
        "residuo_gastrico_ml": residual,
        "evidencia": f"{formula} por {via} a {rate} ml/h",
    }


def _advice(text: str, deadline: str) -> dict:
    return {**task(text, deadline), "responsable_sugerido": "medico"}
