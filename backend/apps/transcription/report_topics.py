"""Temas de un informe: agrupan sus secciones y son la unidad de validación.

El autor valida un informe tema por tema («Diagnóstico y evaluación», «Tratamiento»…), no
sección por sección. Esta es la única fuente de la agrupación: la API la entrega ya armada.
"""

from pydantic import BaseModel

TOPIC_DEFINITIONS: list[tuple[str, str, list[str]]] = [
    (
        "assessment",
        "Diagnóstico y evaluación",
        [
            "ingreso",
            "resumen_24h",
            "diagnosticos",
            "evaluacion",
            "hallazgos",
            "motivo_interconsulta",
            "solicitado_por",
            "valoracion_por_sistemas",
            "evaluacion_respiratoria",
            "evaluacion_motora",
            "tipo_atencion",
            "examenes_revisados",
        ],
    ),
    (
        "vitals",
        "Signos vitales y soporte",
        [
            "control_hemodinamico",
            "control_respiratorio",
            "ventilacion_mecanica",
            "sedoanalgesia_neuro",
            "balance_hidrico",
            "terapia_reemplazo_renal",
            "escalas",
        ],
    ),
    (
        "treatment",
        "Tratamiento",
        [
            "drogas_infusion",
            "medicamentos",
            "antimicrobianos",
            "nutricion",
            "profilaxis",
            "intervenciones",
            "cambios_parametros_vm_sugeridos",
            "indicaciones",
            "procedimientos",
        ],
    ),
    (
        "devices",
        "Dispositivos y cuidados",
        [
            "dispositivos_invasivos",
            "bundles_iaas",
            "piel",
            "cuidados_basicos",
            "eliminacion",
            "alimentacion",
            "contencion",
        ],
    ),
    (
        "exams",
        "Exámenes y cultivos",
        ["examenes", "cultivos", "toma_examenes", "toma_muestras", "examenes_sugeridos"],
    ),
    ("alerts", "Alertas y alergias", ["alertas", "alergias", "eventos_adversos"]),
    (
        "plan",
        "Plan y pendientes",
        [
            "pendientes",
            "metas_del_dia",
            "objetivos_terapeuticos",
            "recomendaciones_al_tratante",
            "recomendaciones_equipo",
            "interconsultas_solicitadas",
            "seguimiento",
            "traslados",
            "novedades_informadas",
            "entrega_turno",
            "egreso",
        ],
    ),
    (
        "family",
        "Familia y observaciones",
        ["comunicacion_familia", "educacion_familia", "observaciones_no_estructuradas"],
    ),
]
OTHER_TOPIC = ("other", "Otros")
# Los metadatos son el encabezado del informe, no un tema a validar.
HEADER_SECTIONS = frozenset({"metadatos"})


class Topic(BaseModel):
    id: str
    label: str
    sections: list[str]


def group_sections(section_keys: list[str]) -> list[Topic]:
    """Los temas que tienen alguna de las secciones dadas (en el orden de las secciones)."""
    known = {key for _, _, keys in TOPIC_DEFINITIONS for key in keys}
    topics = [
        Topic(id=topic_id, label=label, sections=[k for k in section_keys if k in keys])
        for topic_id, label, keys in TOPIC_DEFINITIONS
    ]
    others = [k for k in section_keys if k not in known and k not in HEADER_SECTIONS]
    topics.append(Topic(id=OTHER_TOPIC[0], label=OTHER_TOPIC[1], sections=others))
    return [topic for topic in topics if topic.sections]
