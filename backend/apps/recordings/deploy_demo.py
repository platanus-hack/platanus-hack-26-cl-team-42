"""Datos de la demo desplegada: un médico, dos kinesiólogos, tres pacientes y un dictado listo.

Tomás Werth (médico) deja un informe de cada paciente y los traspasa a Cristóbal Tubino
(kinesiólogo). El audio de Cristóbal sobre Clemente Vial (``sample_audios/demo``) trae su
transcripción y su registro ya en la caché: al cargarlo se alerta que el cultivo de aspirado
traqueal, negativo, no está en su informe, y se abre un conflicto con el informe de Tomás
(RASS -4 frente a RASS -1).
"""

from datetime import timedelta
from pathlib import Path

from django.utils import timezone

# (correo, nombre, profesión): @localhost para que la rotación de claves y el selector las cubran.
STAFF = [
    ("tomas.werth@localhost", "Tomás Werth", "medico"),
    ("cristobal.tubino@localhost", "Cristóbal Tubino", "kinesiologia"),
    ("nelson.salazar@localhost", "Nelson Salazar", "kinesiologia"),
]
# (identificador, nombre, cama)
PATIENTS = [
    ("20.111.111-1", "María Jesús Navarrete", "Box 3"),
    ("20.222.222-2", "Clemente Vial", "Box 5"),
    ("20.333.333-3", "Agustin Reyman", "Box 8"),
]
CLEMENTE = "Clemente Vial"
# Hace cuántas horas dictó Tomás cada informe (la «última visita»). Con la criticidad de cada
# caso da tres urgencias distintas: Clemente (crítico, cada 2 h) toca visitarlo ahora; María Jesús
# (moderada, cada 8 h) pronto; Agustin (estable, cada 12 h) tiene la visita al día.
TOMAS_HOURS_AGO = {"María Jesús Navarrete": 5.5, CLEMENTE: 9.0, "Agustin Reyman": 2.0}
HANDOFF_NOTE = "Entrego mis tres pacientes del turno. Clemente: pendiente evaluar destete."

AUDIO_DIR = Path(__file__).parents[3] / "sample_audios" / "demo"
TUBINO_AUDIO = AUDIO_DIR / "Klgo. Tubino - Kinesiología - 21-11-2026 10-00.wav"
# Se dicta tal cual (y es la transcripción cacheada del audio).
TUBINO_TEXT = (
    "Evolución de kinesiología, Clemente Vial, cama cinco, día cuatro de estadía en UCI. "
    "Paciente en ventilación mecánica invasiva por tubo orotraqueal número siete coma cinco, "
    "modo volumen control, volumen corriente cuatrocientos veinte, PEEP diez, FiO2 cuarenta, "
    "frecuencia programada dieciocho, presión plateau veinticinco. "
    "Al examen, crépitos basales bilaterales y roncus difusos, secreciones abundantes "
    "mucopurulentas, tos inefectiva. Post aspiración satura noventa y siete por ciento. "
    "Escala de Richmond menos uno, paciente despierto, obedece órdenes simples. "
    "Movilización en el borde de la cama, escala IMS tres, con buena tolerancia hemodinámica. "
    "Se realiza aspiración de secreciones y kinesioterapia respiratoria. "
    "Objetivo: preparar prueba de ventilación espontánea para mañana."
)


def tomas_reports(bed_by_name: dict[str, str]) -> dict[str, dict]:
    """El informe de Tomás por paciente (nombre -> dictado), con sus pendientes y escalas."""
    return {
        "María Jesús Navarrete": medico(
            bed_by_name["María Jesús Navarrete"],
            2,
            dx=("Insuficiencia respiratoria por neumonía adquirida en la comunidad", "J18.9"),
            let="Sin limitación del esfuerzo terapéutico; manejo completo.",
            summary="Neumonía comunitaria en alto flujo, mejoría gasométrica; evaluar descenso.",
            resp="Cánula nasal de alto flujo",
            sat=94,
            meds=[med("ceftriaxona", 2, "g", "EV", "cada 24 h")],
            devices=[device("Vía venosa periférica", "antebrazo izquierdo")],
            scales=[
                scale("RASS", 0, "alerta y tranquila"),
                scale("SOFA", 6, "disfunción moderada"),
            ],
            alerts=[alert("Requerimiento de oxígeno aún elevado", "media")],
            pending=[task("Control de gases arteriales", "en 4 h")],
            indications=[task("Descender FiO2 si saturación >= 94 %", "durante el turno")],
        ),
        CLEMENTE: medico(
            bed_by_name[CLEMENTE],
            4,
            dx=(
                "Shock séptico de foco pulmonar, sospecha de neumonía asociada a ventilación",
                "J95.89",
            ),
            let="Sin limitación del esfuerzo terapéutico; manejo completo.",
            summary=(
                "Shock séptico con noradrenalina en descenso, en VMI y sedación profunda; "
                "se espera el resultado del cultivo de aspirado traqueal."
            ),
            resp="Ventilación mecánica invasiva",
            sat=95,
            drugs=[drug("norepinefrina", 0.08, "descenso")],
            meds=[med("meropenem", 1, "g", "EV", "cada 8 h")],
            devices=[device("TET", "orotraqueal"), device("CVC", "yugular derecha")],
            scales=[scale("RASS", -4, "sedación profunda")],
            alerts=[alert("Sospecha de neumonía asociada a ventilación mecánica", "media")],
            pending=[task("Resultado del cultivo de aspirado traqueal", "hoy")],
            indications=[task("Mantener sedación profunda mientras dure el shock", "24 h")],
        ),
        "Agustin Reyman": medico(
            bed_by_name["Agustin Reyman"],
            3,
            dx=("Traumatismo encefalocraneano leve", "S06.0"),
            let="Sin limitación del esfuerzo terapéutico; manejo completo.",
            summary="TEC leve, despierto y orientado, sin déficit; observación neurológica.",
            resp="Cánula nasal de bajo flujo",
            sat=98,
            meds=[med("levetiracetam", 500, "mg", "EV", "cada 12 h")],
            devices=[device("Vía venosa periférica", "antebrazo derecho")],
            scales=[scale("Glasgow", 15, "sin compromiso de conciencia")],
            pending=[task("TAC de cerebro de control", "mañana")],
        ),
    }


def tubino_record() -> dict:
    """Registro de kinesiología que sale del dictado de Cristóbal (lo que cachea la extracción)."""
    return {
        "metadatos": {
            **meta("kinesiologia", "Cristóbal Tubino", "Box 5", 4),
            "especialidad": None,
            "fecha_hora_registro": "2026-11-21T10:00:00-03:00",
            "tipo_registro": "evolucion",
            "turno": "dia",
        },
        "control_hemodinamico": [],
        "control_respiratorio": [
            {
                "hora": "10:00",
                "frecuencia_respiratoria": None,
                "saturacion_o2": 97,
                "soporte": "VMI",
                "fio2": 40,
                "flujo_l_min": None,
                "evidencia": "post aspiración satura noventa y siete",
            }
        ],
        "drogas_infusion": [],
        "medicamentos": [],
        "escalas": [
            {
                "nombre": "RASS",
                "puntaje": -1,
                "interpretacion": "despierto, obedece órdenes simples",
                "evidencia": "Escala de Richmond menos uno, paciente despierto",
            },
            {
                "nombre": "IMS",
                "puntaje": 3,
                "interpretacion": "sedestación en el borde de la cama",
                "evidencia": "escala IMS tres",
            },
        ],
        "dispositivos_invasivos": [
            {
                "tipo": "TET",
                "ubicacion": "orotraqueal",
                "fecha_instalacion": None,
                "dias_instalado": None,
                "estado": None,
                "signos_infeccion": None,
                "accion": "mantenido",
                "evidencia": "tubo orotraqueal número siete coma cinco",
            }
        ],
        "alergias": [],
        "alertas": [],
        "indicaciones": [],
        "pendientes": [],
        "observaciones_no_estructuradas": None,
        "tipo_atencion": ["respiratoria", "motora"],
        "evaluacion_respiratoria": {
            "patron": "acoplado al ventilador",
            "auscultacion": "crépitos basales bilaterales y roncus difusos",
            "tos": "inefectiva",
            "secreciones": {"cantidad": "abundante", "aspecto": "mucopurulentas"},
            "ventilacion_mecanica": {
                "via_aerea": {
                    "tipo": "TET",
                    "numero": "7.5",
                    "fijacion_cm": None,
                    "presion_cuff_cmh2o": None,
                },
                "modo": "VCV",
                "volumen_corriente_ml": 420,
                "peep_cmh2o": 10,
                "fio2": 40,
                "fr_programada": 18,
                "presion_soporte_cmh2o": None,
                "presion_plateau_cmh2o": 25,
                "presion_peak_cmh2o": None,
                "driving_pressure_cmh2o": None,
                "pafi": None,
                "posicion_prono": None,
                "weaning": None,
                "evidencia": "volumen control, volumen corriente cuatrocientos veinte, PEEP diez",
            },
            "evidencia": "crépitos basales bilaterales, secreciones abundantes mucopurulentas",
        },
        "evaluacion_motora": {
            "mrc_total": None,
            "mrc_segmentos": [],
            "ims": 3,
            "nivel_movilizacion": "borde de la cama",
            "tolerancia": "buena tolerancia hemodinámica",
            "evidencia": "Movilización en el borde de la cama, escala IMS tres",
        },
        "intervenciones": [
            {
                "tecnica": "aspiración de secreciones por TET",
                "dosificacion": None,
                "respuesta": "satura 97%",
                "evidencia": "Se realiza aspiración de secreciones",
            },
            {
                "tecnica": "kinesioterapia respiratoria",
                "dosificacion": None,
                "respuesta": None,
                "evidencia": "kinesioterapia respiratoria",
            },
        ],
        "cambios_parametros_vm_sugeridos": [],
        "objetivos_terapeuticos": [
            {
                "objetivo": "Preparar prueba de ventilación espontánea",
                "plazo": "mañana",
                "evidencia": "preparar prueba de ventilación espontánea para mañana",
            }
        ],
        "recomendaciones_equipo": [],
    }


def clemente_evidence() -> list[dict]:
    """Exámenes de Clemente: entre ellos el cultivo negativo que el informe de Cristóbal omite."""
    return [
        {
            "kind": "culture",
            "title": "Cultivo de aspirado traqueal",
            "hours_ago": 5.0,
            "results": [],
            "findings": "Sin desarrollo bacteriano a las 48 horas (negativo).",
        },
        {
            "kind": "lab",
            "title": "Hemograma y PCR",
            "hours_ago": 6.0,
            "results": [
                {"name": "Leucocitos", "value": "14.2"},
                {"name": "PCR", "value": "160"},
            ],
            "findings": "",
        },
    ]


def evidence_time(hours_ago: float):
    return timezone.now() - timedelta(hours=hours_ago)


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
